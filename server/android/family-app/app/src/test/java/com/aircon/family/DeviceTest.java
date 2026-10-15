package com.aircon.family;

import java.util.List;
import java.util.Map;
import org.junit.Test;
import static com.aircon.family.TestMaps.*;
import static org.junit.Assert.*;

public class DeviceTest {
    @Test public void parsesTheContractEntryIntoPlainValues() {
        Device d=Device.from(device(DOOR,"현관문","현관","door_sensor",list("contact","battery"),
            map("contact","closed","battery_percent",87,"battery_low",false),1792130000.0));
        assertEquals(DOOR,d.id);assertEquals("현관문",d.name);assertEquals("현관",d.room);assertEquals("door_sensor",d.type);
        assertEquals(List.of("contact","battery"),d.capabilities);
        assertEquals(87.0,(Double)d.state.get("battery_percent"),0);assertEquals(Boolean.FALSE,d.state.get("battery_low"));
        assertEquals(1792130000.0,d.reportedAt,0);assertFalse(d.controllable);
        assertTrue(Device.from(device(AIRCON,"에어컨","","air_conditioner",list(),map(),null)).controllable);
    }
    @Test public void unknownTypesBlocksAndStateKeysAreKeptButMalformedOnesDropped() {
        Map<String,Object> state=map("illuminance_lux",120,"Bad-Key","x","nan",Double.NaN,"label","  \u0007켜짐​ ","list",list(1),"none",null);
        Device d=Device.from(device(DOOR,"센서","","air_purifier",list("filter","filter","Bad Cap",7,"pm25"),state,-5));
        assertEquals("air_purifier",d.type);assertEquals("other",d.category());
        assertEquals(List.of("filter","pm25"),d.capabilities);
        assertEquals(120.0,(Double)d.state.get("illuminance_lux"),0);
        assertFalse(d.state.containsKey("Bad-Key"));assertFalse(d.state.containsKey("nan"));assertFalse(d.state.containsKey("list"));
        assertEquals("켜짐",d.state.get("label"));
        assertTrue(d.state.containsKey("none"));assertNull(d.state.get("none"));
        assertNull("Non-positive report times mean never reported",d.reportedAt);
        assertEquals("unknown",Device.from(device(DOOR,"x","","Not A Type",list(),map(),null)).type);
    }
    @Test public void entriesWithoutAUsableIdAreSkippedAndDuplicatesKeepTheFirst() {
        List<Device> devices=Device.list(list(
            device("",  "a","","door_sensor",list(),map(),null),
            device("../x","b","","door_sensor",list(),map(),null),
            "not a map",
            device(DOOR,"first","","door_sensor",list(),map(),null),
            device(DOOR,"second","","door_sensor",list(),map(),null)));
        assertEquals(1,devices.size());assertEquals("first",devices.get(0).name);
        assertNull(Device.from(map("name","no id","type","light")));
    }
    @Test public void missingNameFallsBackToTheTypeName() {
        assertEquals("에어컨",Device.from(device(AIRCON,"","","air_conditioner",list(),map(),null)).name);
        assertEquals("문",Device.from(device(DOOR,null,null,"door_sensor",list(),map(),null)).name);
        assertEquals("",Device.from(device(DOOR,null,null,"door_sensor",list(),map(),null)).room);
    }
    @Test public void categoryOfEachTypeFollowsTheChosenGroups() {
        assertEquals("hvac",DeviceCategory.of("air_conditioner"));
        assertEquals("light",DeviceCategory.of("light"));
        assertEquals("security",DeviceCategory.of("door_sensor"));assertEquals("security",DeviceCategory.of("motion_sensor"));
        assertEquals("environment",DeviceCategory.of("climate_sensor"));
        assertEquals("safety",DeviceCategory.of("leak_sensor"));assertEquals("safety",DeviceCategory.of("smoke_sensor"));
        assertEquals("power",DeviceCategory.of("plug"));
        assertEquals("other",DeviceCategory.of("robot_vacuum"));assertEquals("other",DeviceCategory.of(null));
        assertEquals("냉난방",DeviceCategory.label("hvac"));assertEquals("보안",DeviceCategory.label("security"));
        assertEquals("환경",DeviceCategory.label("environment"));assertEquals("안전",DeviceCategory.label("safety"));
        assertEquals("전력",DeviceCategory.label("power"));assertEquals("조명",DeviceCategory.label("light"));assertEquals("기타",DeviceCategory.label("other"));
    }
    @Test public void presentCategoriesKeepTheChipOrder() {
        Device plug=Device.from(device("p1","플러그","","plug",list(),map(),null));
        assertEquals(List.of("hvac","security","environment","power"),
            DeviceCategory.present(List.of(plug,door("closed",null,null),climate(25.0,50.0,null),aircon(map()))));
    }
    @Test public void shortNameDropsOnlyASeparateRoomWord() {
        assertEquals("에어컨",aircon(map()).shortName());
        assertEquals("거실에어컨",Device.from(device(AIRCON,"거실에어컨","거실","air_conditioner",list(),map(),null)).shortName());
        assertEquals("거실",Device.from(device(AIRCON,"거실","거실","air_conditioner",list(),map(),null)).shortName());
        assertEquals("안방 에어컨",Device.from(device(AIRCON,"안방 에어컨","거실","air_conditioner",list(),map(),null)).shortName());
        assertEquals("현관문",Device.from(device(DOOR,"현관문","","door_sensor",list(),map(),null)).shortName());
        assertEquals("현관문",Device.from(device(DOOR,"현관문","현관","door_sensor",list(),map(),null)).shortName());
    }
    @Test public void batterySensorsGoStaleAfterSixHoursButMainsDevicesNever() {
        double now=1_800_000_000;
        assertFalse(door("closed",80.0,now-6*3600).stale(now));
        assertTrue(door("closed",80.0,now-6*3600-1).stale(now));
        assertFalse("Never reported is not judged",door("closed",80.0,null).stale(now));
        Device mains=Device.from(device("plug","플러그","","plug",list("power"),map("power",true),now-86400));
        assertFalse(mains.stale(now));
        Device lowFlag=Device.from(device(DOOR,"문","","door_sensor",list("contact"),map("battery_low",true),now));
        assertTrue("A battery_low key alone makes it a battery sensor",lowFlag.hasBattery());
    }
    @Test public void lowBatteryIsTheFlagOrTwentyPercentOrLess() {
        assertTrue(door("closed",20.0,null).batteryLow());assertFalse(door("closed",21.0,null).batteryLow());
        assertEquals(Integer.valueOf(12),door("closed",12.4,null).batteryPercent());
        assertFalse(door("closed",null,null).batteryLow());
        assertTrue(Device.from(device(DOOR,"문","","door_sensor",list("battery"),map("battery_low",true,"battery_percent",60),null)).batteryLow());
    }
    @Test public void powerUnderstandsBooleansStringsAndAModeWithoutPower() {
        assertEquals(Boolean.TRUE,aircon(map("power",true)).power());
        assertEquals(Boolean.FALSE,aircon(map("power","off")).power());
        assertEquals(Boolean.TRUE,aircon(map("mode","cool")).power());
        assertNull(aircon(map()).power());
        assertEquals("open",door("open",null,null).contact());assertNull(door(null,null,null).contact());
    }
}
