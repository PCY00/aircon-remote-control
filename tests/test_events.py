import asyncio

from app.events import EventHub, format_sse


def test_event_hub_delivers_cross_callback_updates_and_formats_sse() -> None:
    async def scenario() -> dict[str, object]:
        hub = EventHub(queue_size=2)
        hub.start()
        async with hub.subscribe() as queue:
            published = hub.publish("sensor.updated", {"sensor": {"device_id": "door"}})
            received = await asyncio.wait_for(queue.get(), timeout=1)
            assert received == published
        await hub.stop()
        return published

    event = asyncio.run(scenario())
    encoded = format_sse(event)
    assert encoded.startswith("id: 1\ndata: ")
    assert '"type":"sensor.updated"' in encoded
    assert encoded.endswith("\n\n")
