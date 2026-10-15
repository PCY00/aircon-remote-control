package com.aircon.family;

import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import static com.aircon.family.TestMaps.*;
import static org.junit.Assert.*;

public class AttentionTest {
    private static final double NOW=1_800_000_000;
    private static ControlStatus control(String state,double at) {
        return ControlStatus.from(map("online",true,"can_control",true,"devices",list(map("id",AIRCON,"name","거실 에어컨")),
            "latest_command",map("id","c1","device_id",AIRCON,"action","cool_24_auto","state",state,"created_at",at,"updated_at",at)));
    }
    private static List<String> keys(List<Attention.Item> items) {
        List<String> keys=new ArrayList<>();for(Attention.Item item:items) keys.add(item.key);return keys;
    }

    @Test public void anOpenDoorCountsFromItsLatestOpenRecord() {
        List<AppEvent> events=List.of(event(2,"sensor.door_changed",NOW-12*60,map("state","open","device_id",DOOR)),
            event(1,"sensor.door_changed",NOW-3600,map("state","closed","device_id",DOOR)));
        List<Attention.Item> items=Attention.compute(inventory(NOW,true,door("open",90.0,NOW-30)),events,null,NOW);
        assertEquals(1,items.size());
        Attention.Item item=items.get(0);
        assertEquals("현관문이 열려 있어요",item.title);assertEquals("12분째",item.detail);
        assertEquals(Attention.Tone.DANGER,item.tone);assertEquals(DOOR,item.deviceId);assertEquals("security",item.category);
        assertEquals("Without a matching record the report time is used","3분째",
            Attention.compute(inventory(NOW,true,door("open",90.0,NOW-180)),List.of(),null,NOW).get(0).detail);
        assertEquals("방금 열렸어요",Attention.compute(inventory(NOW,true,door("open",90.0,NOW-10)),List.of(),null,NOW).get(0).detail);
        assertTrue("A closed door needs nothing",Attention.compute(inventory(NOW,true,door("closed",90.0,NOW)),List.of(),null,NOW).isEmpty());
    }
    @Test public void olderRecordsWithoutDeviceIdStillTimeTheDoor() {
        List<AppEvent> events=List.of(event(1,"sensor.door_changed",NOW-7200,map("state","open")));
        assertEquals("2시간째",Attention.compute(inventory(NOW,true,door("open",null,null)),events,null,NOW).get(0).detail);
    }
    @Test public void lowBatteryIsAWarning() {
        Attention.Item item=Attention.compute(inventory(NOW,true,door("closed",12.0,NOW)),List.of(),null,NOW).get(0);
        assertEquals("현관문",item.title);assertEquals("배터리 12%",item.detail);assertEquals(Attention.Tone.WARNING,item.tone);
        assertEquals("device",item.category);
    }
    @Test public void staleSensorsAreNeutralUnlessTheHubIsDown() {
        Device quiet=climate(25.0,50.0,NOW-7*3600);
        Attention.Item item=Attention.compute(inventory(NOW,true,quiet),List.of(),null,NOW).get(0);
        assertEquals("거실 온습도",item.title);assertEquals("응답 없음 · 7시간",item.detail);assertEquals(Attention.Tone.NEUTRAL,item.tone);
        List<Attention.Item> hubDown=Attention.compute(inventory(NOW-3600,true,quiet),List.of(),null,NOW);
        assertEquals(List.of("hub"),keys(hubDown));
        assertEquals("Pi와 연결이 끊겼어요",hubDown.get(0).title);assertEquals("마지막 연결 1시간 전",hubDown.get(0).detail);
        assertEquals(List.of("hub"),keys(Attention.compute(inventory(NOW,false),List.of(),null,NOW)));
    }
    @Test public void aFailedOrUnknownCommandStaysForTenMinutes() {
        Inventory inventory=inventory(NOW,true,aircon(map()));
        Attention.Item failed=Attention.compute(inventory,List.of(),control("failed",NOW-120),NOW).get(0);
        assertEquals("거실 에어컨 명령이 전달되지 않았어요",failed.title);assertEquals("냉방 24°C · 자동 · 2분 전",failed.detail);
        assertEquals(AIRCON,failed.deviceId);assertEquals(Attention.Tone.DANGER,failed.tone);
        assertEquals(1,Attention.compute(inventory,List.of(),control("unknown",NOW-600),NOW).size());
        assertTrue(Attention.compute(inventory,List.of(),control("unknown",NOW-601),NOW).isEmpty());
        assertTrue(Attention.compute(inventory,List.of(),control("sent",NOW),NOW).isEmpty());
        assertTrue(Attention.compute(inventory,List.of(),control("queued",NOW),NOW).isEmpty());
    }
    @Test public void anAutomationWarningCountsOnlyUntilItIsResolved() {
        List<AppEvent> active=List.of(event(2,"automation.warning_triggered",NOW-300,map()),event(1,"automation.warning_resolved",NOW-900,map()));
        Attention.Item item=Attention.compute(inventory(NOW,true),active,null,NOW).get(0);
        assertEquals("자동화 경고가 켜져 있어요",item.title);assertEquals("5분 전",item.detail);assertNull(item.deviceId);
        assertEquals("automation",item.category);
        List<AppEvent> resolved=List.of(event(3,"automation.warning_resolved",NOW-60,map()),event(2,"automation.warning_triggered",NOW-300,map()));
        assertTrue(Attention.compute(inventory(NOW,true),resolved,null,NOW).isEmpty());
    }
    @Test public void dangerComesFirstThenWarningsThenNeutralItems() {
        Device quiet=Device.from(device("cccccccccccccccccccccccccccccccc","창문","","door_sensor",list("battery"),map("contact","closed","battery_percent",80),NOW-8*3600));
        List<Attention.Item> items=Attention.compute(inventory(NOW,true,quiet,door("open",10.0,NOW)),
            List.of(event(1,"automation.warning_triggered",NOW,map())),control("failed",NOW),NOW);
        assertEquals(List.of("door:"+DOOR,"command:c1","automation:1","battery:"+DOOR,"stale:cccccccccccccccccccccccccccccccc"),keys(items));
        assertEquals(1,Attention.filter(items,"security").size());assertEquals(3,Attention.filter(items,"device").size());
        assertEquals(5,Attention.filter(items,"all").size());
        assertTrue(Attention.compute(null,List.of(),null,NOW).isEmpty());
    }
    @Test public void changedAtIsTheDoorsLatestRecord() {
        List<AppEvent> events=List.of(event(3,"sensor.climate_report",NOW,map("device_id",CLIMATE)),
            event(2,"sensor.door_changed",NOW-40,map("state","closed","device_id",DOOR)));
        assertEquals(NOW-40,Attention.changedAt(door("closed",null,null),events),0);
        assertNull(Attention.changedAt(climate(25.0,50.0,NOW),events));
        assertNull(Attention.changedAt(door("closed",null,null),List.of()));
    }
}
