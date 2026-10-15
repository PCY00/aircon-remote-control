package com.aircon.family;

import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import static com.aircon.family.TestMaps.*;
import static org.junit.Assert.*;

public class InventoryTest {
    private static final double NOW=1_800_000_000;
    private static ControlStatus control(boolean online,Object latest,Object... devices) {
        return ControlStatus.from(map("online",online,"can_control",true,"devices",list(devices),"latest_command",latest));
    }
    private static Object command(String device,String action,String state,double at) {
        return map("id","c1","device_id",device,"action",action,"state",state,"created_at",at-2,"updated_at",at,"expires_at",at+30);
    }

    @Test public void readsTheDeviceListReply() {
        Inventory inventory=Inventory.from(map("devices",list(device(DOOR,"현관문","현관","door_sensor",list("contact"),map("contact","open"),NOW)),
            "updated_at",NOW-30,"hub_online",true));
        assertEquals(1,inventory.devices.size());assertEquals(NOW-30,inventory.updatedAt,0);assertEquals(Boolean.TRUE,inventory.hubOnline);
        assertFalse(inventory.fallback);assertFalse(inventory.neverReported());
        assertEquals("현관문",inventory.find(DOOR).name);assertNull(inventory.find("missing"));
        assertEquals("현관문",inventory.names().get(DOOR));
        Inventory empty=Inventory.from(map("devices",list(),"updated_at",null,"hub_online",false));
        assertTrue("A hub that never sent a list",empty.neverReported());
    }
    @Test public void eventsAndControlStatusParseFromPlainValues() {
        AppEvent event=AppEvent.from(map("id",7,"kind","sensor.door_changed","received_at",NOW,"payload",map("state","open","device_id",DOOR)));
        assertEquals(7,event.id);assertEquals(DOOR,event.deviceId);assertEquals("open",event.doorState());assertEquals("security",event.alertCategory());
        assertNull(AppEvent.from(map("kind","","received_at",NOW)));
        assertNull("Older records have no device_id",AppEvent.from(map("kind","sensor.climate_report","payload",map("temperature_c",25))).deviceId);
        List<AppEvent> sorted=AppEvent.list(list(map("id",1,"kind","a","received_at",NOW-10),map("id",2,"kind","b","received_at",NOW),"junk"));
        assertEquals("b",sorted.get(0).kind);assertEquals(2,sorted.size());
        ControlStatus control=control(true,command(AIRCON,"cool_24_auto","sent",NOW),map("id",AIRCON,"name","거실 에어컨"));
        assertTrue(control.online);assertTrue(control.canControl);assertTrue(control.has(AIRCON));
        assertEquals("거실 에어컨",control.deviceName(AIRCON));assertEquals(NOW,control.latest.time(),0);
        assertNotNull(control.latestFor(AIRCON));assertNull(control.latestFor("other"));
        assertNull(control(false,null).latest);
    }
    @Test public void olderServerFallbackUsesTheControlListAndTheLatestRecords() {
        List<AppEvent> events=new ArrayList<>();
        events.add(event(5,"sensor.climate_report",NOW-60,map("temperature_c",25.1,"humidity_percent",48)));
        events.add(event(4,"sensor.door_changed",NOW-120,map("state","open")));
        events.add(event(3,"sensor.door_changed",NOW-600,map("state","closed")));
        Inventory inventory=Inventory.effective(null,control(true,command(AIRCON,"cool_24_low","sent",NOW),map("id",AIRCON,"name","거실 에어컨")),events);
        assertTrue(inventory.fallback);assertEquals(3,inventory.devices.size());
        Device aircon=inventory.devices.get(0);
        assertEquals("air_conditioner",aircon.type);assertTrue(aircon.controllable);assertEquals("",aircon.room);
        assertEquals(Inventory.AIRCON_CAPABILITIES,aircon.capabilities);
        assertEquals("Last sent command is the inferred state","냉방 24°",DeviceText.aircon(aircon));
        assertEquals(Boolean.TRUE,aircon.state.get("inferred"));
        Device door=inventory.devices.get(1), climate=inventory.devices.get(2);
        assertEquals(Inventory.FALLBACK_DOOR,door.id);assertEquals("door_sensor",door.type);assertEquals("open",door.contact());
        assertEquals(NOW-120,door.reportedAt,0);assertEquals("문",door.name);
        assertFalse("No battery block, so a quiet door is never 응답 없음",door.hasBattery());
        assertEquals(Inventory.FALLBACK_CLIMATE,climate.id);assertEquals(25.1,climate.number("temperature_c"),0);
    }
    @Test public void fallbackSensorsTakeTheRecordDeviceIdWhenThePiSendsIt() {
        List<AppEvent> events=List.of(event(1,"sensor.door_changed",NOW,map("state","closed","device_id",DOOR)));
        Inventory inventory=Inventory.fallback(control(true,null),events);
        assertEquals(DOOR,inventory.devices.get(0).id);
    }
    @Test public void unsentOrUnknownCommandsLeaveTheAirconStateUnknown() {
        Object device=map("id",AIRCON,"name","에어컨");
        assertEquals("상태 모름",DeviceText.aircon(Inventory.fallback(control(true,command(AIRCON,"cool_24_auto","failed",NOW),device),List.of()).devices.get(0)));
        assertEquals("상태 모름",DeviceText.aircon(Inventory.fallback(control(true,command("other","power_off","sent",NOW),device),List.of()).devices.get(0)));
        assertEquals("꺼짐",DeviceText.aircon(Inventory.fallback(control(true,command(AIRCON,"power_off","sent",NOW),device),List.of()).devices.get(0)));
        assertEquals("제습",DeviceText.aircon(Inventory.fallback(control(true,command(AIRCON,"mode_dry","sent",NOW),device),List.of()).devices.get(0)));
        assertNull("A toggle says nothing about the state",Inventory.inferred("swing_toggle"));
        assertNull(Inventory.inferred("cool_x_auto"));
    }
    @Test public void aServerListWinsUnlessThePiNeverSentOne() {
        Inventory server=inventory(NOW,true,door("closed",90.0,NOW));
        assertSame(server,Inventory.effective(server,control(true,null),List.of()));
        Inventory never=Inventory.from(map("devices",list(),"updated_at",null,"hub_online",true));
        Inventory used=Inventory.effective(never,control(true,null,map("id",AIRCON,"name","에어컨")),List.of());
        assertTrue("0.7 server with a 0.6 Pi still shows the aircon",used.fallback);assertEquals(1,used.devices.size());
        assertTrue(Inventory.effective(null,null,List.of()).devices.isEmpty());
    }
    @Test public void hubProblemMeansOfflineOrAListOlderThanTenMinutes() {
        assertFalse(inventory(NOW-600,true).hubProblem(NOW));
        assertTrue(inventory(NOW-601,true).hubProblem(NOW));
        assertTrue(inventory(NOW,false).hubProblem(NOW));
        assertFalse("Unknown is not a problem",inventory(NOW,null).hubProblem(NOW));
        assertTrue("Fallback: Pi offline with aircons",Inventory.fallback(control(false,null,map("id",AIRCON,"name","에어컨")),List.of()).hubProblem(NOW));
        assertFalse("Fallback: a home without any hub sign",Inventory.fallback(control(false,null),List.of()).hubProblem(NOW));
        assertFalse("Fallback before the control answer",Inventory.fallback(null,List.of(event(1,"hub.connection_test",NOW,map()))).hubProblem(NOW));
    }
}
