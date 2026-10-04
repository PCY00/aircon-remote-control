"""FastAPI entry point for the air-conditioner controller."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.automations.service import AutomationService
from app.automations.store import AutomationNotFoundError, AutomationStore
from app.devices.catalog import (
    DeviceProfileCatalog,
    InvalidProfileError,
    ProfileNotFoundError,
)
from app.devices.commands import DeviceCommandResolver, UnsupportedCommandError
from app.devices.service import DeviceService
from app.devices.store import (
    DeviceNotFoundError,
    DeviceRequestStore,
    InvalidUploadError,
    RegisteredDeviceStore,
    UploadPayload,
)
from app.devices.transport import (
    DeviceTransport,
    InvalidTransmissionError,
    IrCtlTransport,
    MockIrTransport,
    TransportExecutionError,
    TransportUnavailableError,
)
from app.events import EventHub, format_sse
from app.integrations.mqtt import (
    DisabledSensorBridge,
    PahoSensorBridge,
    SensorBridge,
    ZigbeeGatewayRequestError,
    ZigbeeGatewayUnavailableError,
)
from app.ir.backend import IrCtlReceiver, ReceiverBackend
from app.ir.profiles import ProfileRegistry
from app.ir.service import CaptureBusyError, CaptureNotFoundError, CaptureService
from app.ir.store import CaptureStore
from app.sensors.service import SensorService
from app.sensors.store import SensorNotFoundError, SensorStore
from app.settings import Settings, load_settings

WEB_INDEX = Path(__file__).parent / "static" / "index.html"


class CaptureRequest(BaseModel):
    """User-supplied label and profile for one learned command."""

    name: str = Field(min_length=1, max_length=100)
    profile_id: str = "carrier-16214-15597"
    timeout_seconds: float | None = Field(default=None, ge=1, le=300)


class RegisterDeviceRequest(BaseModel):
    """Assign a supported model profile to a named room device."""

    name: str = Field(min_length=1, max_length=100)
    room: str = Field(min_length=1, max_length=100)
    profile_id: str = Field(min_length=1, max_length=200)
    icon: str = Field(default="box", min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    zigbee_friendly_name: str | None = Field(default=None, min_length=1, max_length=200)


class H2BindingRequest(BaseModel):
    """Select an already interviewed Zigbee H2 IR node for this air conditioner."""

    friendly_name: str = Field(min_length=1, max_length=200)


class DeviceCommandRequest(BaseModel):
    """Transport-independent command sent by the UI or a future scene."""

    action: Literal["set_state", "execute"]
    power: bool | None = None
    mode: Literal["cool", "auto", "dry", "fan_only"] | None = None
    temperature_c: int | None = Field(default=None, ge=17, le=30)
    fan: Literal["auto", "low", "medium", "high"] | None = None
    command_id: str | None = Field(default=None, min_length=1, max_length=100)


class SensorMetadataRequest(BaseModel):
    """User-facing sensor identity shared by every dashboard client."""

    display_name: str = Field(min_length=1, max_length=40)
    room: str = Field(min_length=1, max_length=100)
    icon: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")


class PermitJoinRequest(BaseModel):
    """Open Zigbee joining for a short, bounded interval."""

    duration_seconds: int = Field(default=60, ge=30, le=120)


class AutomationRuleRequest(BaseModel):
    """Mutable settings for one server-side automation rule."""

    enabled: bool | None = None
    delay_seconds: int | None = Field(default=None, ge=30, le=86_400)


async def _read_upload(upload: UploadFile, max_bytes: int) -> UploadPayload:
    data = await upload.read(max_bytes + 1)
    await upload.close()
    return UploadPayload(
        filename=upload.filename or "unnamed",
        content_type=upload.content_type,
        data=data,
    )


def create_app(
    settings: Settings | None = None,
    receiver_backend: ReceiverBackend | None = None,
    device_transport: DeviceTransport | None = None,
    sensor_bridge: SensorBridge | None = None,
) -> FastAPI:
    """Application factory used by production and hardware-free tests."""

    resolved_settings = settings or load_settings()
    backend = receiver_backend or IrCtlReceiver(
        resolved_settings.ir_ctl_path,
        resolved_settings.ir_receiver_device,
    )
    service = CaptureService(
        backend=backend,
        store=CaptureStore(resolved_settings.data_dir),
        profiles=ProfileRegistry(),
        default_timeout_seconds=resolved_settings.ir_capture_timeout_seconds,
    )
    catalog = DeviceProfileCatalog(resolved_settings.device_profiles_dir)
    if device_transport is not None:
        transport = device_transport
    elif resolved_settings.ir_transport == "ir-ctl":
        transport = IrCtlTransport(
            resolved_settings.ir_ctl_path,
            resolved_settings.ir_transmitter_device,
            resolved_settings.ir_send_timeout_seconds,
        )
    else:
        transport = MockIrTransport()
    sensor_service = SensorService(
        store=SensorStore(resolved_settings.data_dir),
        base_topic=resolved_settings.mqtt_base_topic,
    )
    if sensor_bridge is not None:
        bridge = sensor_bridge
    elif resolved_settings.mqtt_enabled:
        bridge = PahoSensorBridge(resolved_settings, sensor_service)
    else:
        bridge = DisabledSensorBridge()
    device_service = DeviceService(
        catalog=catalog,
        store=RegisteredDeviceStore(resolved_settings.data_dir),
        resolver=DeviceCommandResolver(catalog),
        transport=transport,
        zigbee_bridge=bridge,
    )
    request_store = DeviceRequestStore(
        resolved_settings.data_dir,
        resolved_settings.max_upload_bytes,
    )
    event_hub = EventHub()
    automation_service = AutomationService(
        store=AutomationStore(resolved_settings.data_dir),
        sensors=sensor_service,
        devices=device_service,
        events=event_hub,
    )
    sensor_service.add_listener(
        lambda sensor: event_hub.publish("sensor.updated", {"sensor": sensor})
    )
    sensor_service.add_listener(automation_service.notify_state_changed)
    device_service.add_listener(
        lambda result: event_hub.publish("device.commanded", result)
    )
    device_service.add_listener(automation_service.notify_state_changed)
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        event_hub.start()
        automation_service.start()
        bridge.start()
        try:
            yield
        finally:
            bridge.stop()
            await automation_service.stop()
            await event_hub.stop()
            await service.shutdown()

    application = FastAPI(
        title="Air Conditioner Remote Controller",
        description="Raspberry Pi IR gateway API",
        version="0.7.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.capture_service = service
    application.state.device_catalog = catalog
    application.state.device_service = device_service
    application.state.device_request_store = request_store
    application.state.device_transport = transport
    application.state.sensor_service = sensor_service
    application.state.sensor_bridge = bridge
    application.state.event_hub = event_hub
    application.state.automation_service = automation_service
    application.mount("/static", StaticFiles(directory=WEB_INDEX.parent), name="static")

    @application.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(WEB_INDEX, media_type="text/html")

    @application.get("/api/v1/system", tags=["system"])
    def system() -> dict[str, str | int]:
        return {
            "service": "aircon-controller",
            "status": "ir-receiver-ready",
            "port": resolved_settings.port,
            "ui": "room-first-smart-home",
        }

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "aircon-controller"}

    @application.get("/api/v1/events", tags=["events"])
    async def event_stream(request: Request) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            ready = {
                "type": "stream.ready",
                "occurred_at": automation_service.evaluate()["evaluated_at"],
                "data": {"message": "live dashboard stream connected"},
            }
            async with event_hub.subscribe() as queue:
                yield format_sse(ready)
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield format_sse(event)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/api/v1/automations", tags=["automations"])
    def list_automations() -> dict[str, object]:
        return {"items": automation_service.list_rules()}

    @application.get("/api/v1/automations/events", tags=["automations"])
    def list_automation_events(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, object]:
        return {"items": automation_service.list_events(limit)}

    @application.patch("/api/v1/automations/{rule_id}", tags=["automations"])
    def update_automation(
        rule_id: str,
        update: AutomationRuleRequest,
    ) -> dict[str, object]:
        if update.enabled is None and update.delay_seconds is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="enabled or delay_seconds is required",
            )
        try:
            return automation_service.update_rule(
                rule_id,
                enabled=update.enabled,
                delay_seconds=update.delay_seconds,
            )
        except AutomationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="automation rule not found",
            ) from exc

    @application.get("/api/v1/sensors/status", tags=["sensors"])
    def sensor_status() -> dict[str, object]:
        return {**bridge.status(), "stored_sensor_count": len(sensor_service.list())}

    @application.get("/api/v1/sensors", tags=["sensors"])
    def list_sensors() -> dict[str, object]:
        return {"items": sensor_service.list()}

    @application.get("/api/v1/sensors/{device_id}", tags=["sensors"])
    def get_sensor(device_id: str) -> dict[str, object]:
        try:
            return sensor_service.get(device_id)
        except SensorNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="sensor not found",
            ) from exc

    @application.get("/api/v1/sensors/{device_id}/events", tags=["sensors"])
    def list_sensor_events(
        device_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, object]:
        try:
            return {"items": sensor_service.list_events(device_id, limit)}
        except SensorNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="sensor not found",
            ) from exc

    @application.patch("/api/v1/sensors/{device_id}/metadata", tags=["sensors"])
    def update_sensor_metadata(
        device_id: str,
        request: SensorMetadataRequest,
    ) -> dict[str, object]:
        try:
            return sensor_service.update_metadata(
                device_id,
                display_name=request.display_name,
                room=request.room,
                icon=request.icon,
            )
        except SensorNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="sensor not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @application.get("/api/v1/zigbee/join", tags=["zigbee"])
    def zigbee_join_status() -> dict[str, object]:
        return bridge.join_status()

    @application.post("/api/v1/zigbee/join", tags=["zigbee"])
    def open_zigbee_join(request: PermitJoinRequest) -> dict[str, object]:
        try:
            return bridge.set_permit_join(request.duration_seconds)
        except ZigbeeGatewayUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ZigbeeGatewayRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    @application.delete("/api/v1/zigbee/join", tags=["zigbee"])
    def close_zigbee_join() -> dict[str, object]:
        try:
            return bridge.set_permit_join(0)
        except ZigbeeGatewayUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ZigbeeGatewayRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    @application.get("/api/v1/zigbee/devices", tags=["zigbee"])
    def list_zigbee_devices() -> dict[str, object]:
        return {"items": bridge.devices()}

    @application.get("/api/v1/device-profiles", tags=["devices"])
    def list_device_profiles() -> dict[str, object]:
        try:
            return {"items": catalog.list()}
        except InvalidProfileError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    @application.get("/api/v1/device-profiles/{profile_id:path}", tags=["devices"])
    def get_device_profile(profile_id: str) -> dict[str, object]:
        try:
            return catalog.detail(profile_id)
        except ProfileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="device profile not found",
            ) from exc
        except InvalidProfileError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    @application.post(
        "/api/v1/device-requests",
        tags=["devices"],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_device_request(
        device_type: Annotated[str, Form(min_length=1, max_length=100)],
        brand: Annotated[str, Form(min_length=1, max_length=100)],
        model: Annotated[str, Form(min_length=1, max_length=100)],
        product_photo: Annotated[UploadFile, File()],
        remote_photo: Annotated[UploadFile | None, File()] = None,
        manual: Annotated[UploadFile | None, File()] = None,
    ) -> dict[str, object]:
        try:
            product = await _read_upload(product_photo, resolved_settings.max_upload_bytes)
            remote = (
                await _read_upload(remote_photo, resolved_settings.max_upload_bytes)
                if remote_photo is not None
                else None
            )
            manual_payload = (
                await _read_upload(manual, resolved_settings.max_upload_bytes)
                if manual is not None
                else None
            )
            return request_store.create(
                device_type=device_type,
                brand=brand,
                model=model,
                product_photo=product,
                remote_photo=remote,
                manual=manual_payload,
            )
        except (InvalidUploadError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @application.post(
        "/api/v1/devices",
        tags=["devices"],
        status_code=status.HTTP_201_CREATED,
    )
    def register_device(request: RegisterDeviceRequest) -> dict[str, object]:
        try:
            return device_service.register(
                name=request.name.strip(),
                room=request.room.strip(),
                profile_id=request.profile_id,
                icon=request.icon,
                zigbee_friendly_name=request.zigbee_friendly_name,
            )
        except ProfileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="unsupported device profile",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except ZigbeeGatewayUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @application.put("/api/v1/devices/{device_id}/zigbee-h2", tags=["devices"])
    def bind_device_h2(device_id: str, request: H2BindingRequest) -> dict[str, object]:
        try:
            return device_service.bind_h2(device_id, request.friendly_name)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="registered device not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ZigbeeGatewayUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.delete("/api/v1/devices/{device_id}/zigbee-h2", tags=["devices"])
    def unbind_device_h2(device_id: str) -> dict[str, object]:
        try:
            return device_service.unbind_h2(device_id)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="registered device not found") from exc

    @application.get("/api/v1/devices", tags=["devices"])
    def list_devices() -> dict[str, object]:
        return {"items": device_service.list()}

    @application.post("/api/v1/devices/{device_id}/commands", tags=["devices"])
    def send_device_command(
        device_id: str,
        request: DeviceCommandRequest,
    ) -> dict[str, object]:
        try:
            return device_service.execute(device_id, request.model_dump(exclude_none=True))
        except DeviceNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="registered device not found",
            ) from exc
        except UnsupportedCommandError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except ZigbeeGatewayUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ZigbeeGatewayRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        except TransportUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except TransportExecutionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        except InvalidTransmissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    @application.get("/api/v1/ir/transmitter", tags=["ir-transmitter"])
    def transmitter_status() -> dict[str, object]:
        return transport.status()

    @application.get("/api/v1/ir/transmissions", tags=["ir-transmitter"])
    def list_transmissions() -> dict[str, object]:
        return {"items": transport.list()}

    @application.get("/api/v1/ir/receiver", tags=["ir-receiver"])
    def receiver_status() -> dict[str, object]:
        return service.receiver_status()

    @application.get("/api/v1/ir/profiles", tags=["ir-receiver"])
    def profiles() -> dict[str, object]:
        return {"items": service.profiles()}

    @application.post(
        "/api/v1/ir/captures",
        tags=["ir-receiver"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_capture(request: CaptureRequest) -> dict[str, object]:
        try:
            return await service.start(
                name=request.name.strip(),
                profile_id=request.profile_id,
                timeout_seconds=request.timeout_seconds,
            )
        except CaptureBusyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "receiver is busy", "active_capture_id": str(exc)},
            ) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @application.get("/api/v1/ir/captures", tags=["ir-receiver"])
    def list_captures() -> dict[str, object]:
        return {"items": service.list()}

    @application.get("/api/v1/ir/captures/{capture_id}", tags=["ir-receiver"])
    def get_capture(capture_id: str) -> dict[str, object]:
        try:
            return service.get(capture_id)
        except CaptureNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="capture not found",
            ) from exc

    @application.post("/api/v1/ir/captures/{capture_id}/cancel", tags=["ir-receiver"])
    async def cancel_capture(capture_id: str) -> dict[str, object]:
        try:
            return await service.cancel(capture_id)
        except CaptureNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="capture not found",
            ) from exc

    @application.delete(
        "/api/v1/ir/captures/{capture_id}",
        tags=["ir-receiver"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_capture(capture_id: str) -> Response:
        try:
            await service.delete(capture_id)
        except CaptureNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="capture not found",
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


app = create_app()
