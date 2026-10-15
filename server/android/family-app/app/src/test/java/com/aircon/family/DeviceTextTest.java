package com.aircon.family;

import java.util.List;
import java.util.Map;
import org.junit.Test;
import static com.aircon.family.TestMaps.*;
import static org.junit.Assert.*;

public class DeviceTextTest {
    private static final double NOW=1_800_000_000;
    private static Device of(String type,Map<String,Object> state) {
        return Device.from(device("d"+type,"기기","","" +type,list(),state,null));
    }

    @Test public void airconTileShowsModeAndSetpointOrOffOrUnknown() {
        assertEquals("냉방 24°",DeviceText.summary(aircon(map("power",true,"mode","cool","setpoint_c",24,"inferred",true)),NOW,null));
        assertEquals("난방 22.5°",DeviceText.summary(aircon(map("power","on","mode","heat","setpoint_c",22.5)),NOW,null));
        assertEquals("제습",DeviceText.summary(aircon(map("power",true,"mode","dry","setpoint_c",24)),NOW,null));
        assertEquals("송풍",DeviceText.summary(aircon(map("power",true,"mode","fan_only")),NOW,null));
        assertEquals("켜짐",DeviceText.summary(aircon(map("power",true)),NOW,null));
        assertEquals("꺼짐",DeviceText.summary(aircon(map("power",false,"mode","cool")),NOW,null));
        assertEquals("상태 모름",DeviceText.summary(aircon(map()),NOW,null));
    }
    @Test public void doorTileShowsTheStateAndHowLongAgo() {
        assertEquals("닫힘 · 3분 전",DeviceText.summary(door("closed",90.0,NOW-3600),NOW,NOW-200));
        assertEquals("Without a record the report time is used","열림 · 1시간 전",DeviceText.summary(door("open",90.0,NOW-3600),NOW,null));
        assertEquals("닫힘 · 방금",DeviceText.summary(door("closed",90.0,NOW-20),NOW,null));
        assertEquals("닫힘",DeviceText.summary(door("closed",90.0,null),NOW,null));
        assertEquals("상태 모름",DeviceText.summary(door(null,90.0,null),NOW,null));
    }
    @Test public void sensorAndPowerTiles() {
        assertEquals("25.1° · 48%",DeviceText.summary(climate(25.14,48.0,NOW),NOW,null));
        assertEquals("25°",DeviceText.summary(climate(25.0,null,NOW),NOW,null));
        assertEquals("측정값 없음",DeviceText.summary(climate(null,null,NOW),NOW,null));
        assertEquals("켜짐 · 70%",DeviceText.summary(of("light",map("power",true,"brightness_percent",70)),NOW,null));
        assertEquals("꺼짐",DeviceText.summary(of("light",map("power",false,"brightness_percent",70)),NOW,null));
        assertEquals("켜짐 · 312W",DeviceText.summary(of("plug",map("power",true,"power_w",312)),NOW,null));
        assertEquals("움직임 감지",DeviceText.summary(of("motion_sensor",map("motion",true)),NOW,null));
        assertEquals("누수 감지",DeviceText.summary(of("leak_sensor",map("leak",true)),NOW,null));
        assertEquals("이상 없음",DeviceText.summary(of("smoke_sensor",map("smoke",false)),NOW,null));
    }
    @Test public void unknownTypesShowTheirFirstStateValue() {
        assertEquals("120",DeviceText.summary(of("lux_meter",map("illuminance_lux",120,"battery_percent",50)),NOW,null));
        assertEquals("필터 교체",DeviceText.summary(of("air_purifier",map("status","필터 교체")),NOW,null));
        assertEquals("켜짐",DeviceText.summary(of("fan",map("running",true)),NOW,null));
        assertEquals("상태 모름",DeviceText.summary(of("fan",map()),NOW,null));
    }
    @Test public void staleTilesSayNoResponse() {
        assertEquals("응답 없음",DeviceText.tile(door("closed",90.0,NOW-7*3600),NOW,null));
        assertEquals("닫힘 · 1시간 전",DeviceText.tile(door("closed",90.0,NOW-3600),NOW,null));
    }
    @Test public void numbersTimesAndParticles() {
        assertEquals("24",DeviceText.number(24.0));assertEquals("25.1",DeviceText.number(25.14));assertEquals("26",DeviceText.number(25.96));
        assertEquals("-3.5",DeviceText.number(-3.5));
        assertEquals("방금",DeviceText.ago(59));assertEquals("1분 전",DeviceText.ago(60));assertEquals("59분 전",DeviceText.ago(3599));
        assertEquals("2시간 전",DeviceText.ago(2*3600+5));assertEquals("3일 전",DeviceText.ago(3*86400));
        assertEquals("1분",DeviceText.duration(10));assertEquals("7시간",DeviceText.duration(7*3600+100));
        assertEquals("현관문이",DeviceText.subject("현관문"));assertEquals("문 센서가",DeviceText.subject("문 센서"));
        assertEquals("창문 1이",DeviceText.subject("창문 1"));assertEquals("창문 2가",DeviceText.subject("창문 2"));
        assertEquals("Door가",DeviceText.subject("Door"));assertEquals("Room이",DeviceText.subject("Room"));
    }
    @Test public void categoryChipsSummariseTheirDevices() {
        Device on=aircon(map("power",true,"mode","cool","setpoint_c",24));
        Device off=Device.from(device("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","안방 에어컨","안방","air_conditioner",list(),map("power",false),null));
        assertEquals("냉방 24°",DeviceText.category("hvac",List.of(on,off),NOW));
        assertEquals("꺼짐",DeviceText.category("hvac",List.of(off),NOW));
        assertEquals("상태 모름",DeviceText.category("hvac",List.of(aircon(map())),NOW));
        assertEquals("2대 켜짐",DeviceText.category("hvac",List.of(on,Device.from(device("c2","작은방 에어컨","","air_conditioner",list(),map("power",true),null))),NOW));
        assertEquals("문 닫힘",DeviceText.category("security",List.of(door("closed",null,null)),NOW));
        Device second=Device.from(device("d2","창문","","door_sensor",list(),map("contact","open"),null));
        assertEquals("문 1개 열림",DeviceText.category("security",List.of(door("closed",null,null),second),NOW));
        Device other=Device.from(device("c9","안방 온습도","안방","climate_sensor",list(),map("temperature_c",26.2,"humidity_percent",52),null));
        assertEquals("25.6° · 50%",DeviceText.category("environment",List.of(climate(25.0,48.0,NOW),other),NOW));
        assertEquals("2개 켜짐",DeviceText.category("light",List.of(of("light",map("power",true)),
            Device.from(device("l2","전등","","light",list(),map("power",true),null))),NOW));
        assertEquals("모두 꺼짐",DeviceText.category("power",List.of(of("plug",map("power",false))),NOW));
        assertEquals("이상 없음",DeviceText.category("safety",List.of(of("leak_sensor",map("leak",false))),NOW));
    }
    @Test public void roomsKeepFirstAppearanceAndShowTheirClimate() {
        Device hall=door("closed",null,null), living=climate(26.2,52.0,NOW), noRoom=Device.from(device("x1","플러그","","plug",list(),map(),null));
        Map<String,List<Device>> rooms=DeviceText.rooms(List.of(hall,noRoom,living,aircon(map())));
        assertEquals(List.of("현관","","거실"),List.copyOf(rooms.keySet()));
        assertEquals(2,rooms.get("거실").size());
        assertEquals("26.2° · 52%",DeviceText.roomClimate(rooms.get("거실")));
        assertNull(DeviceText.roomClimate(rooms.get("현관")));
        assertEquals("공간 미지정",DeviceText.roomLabel(""));assertEquals("거실",DeviceText.roomLabel("거실"));
        assertEquals("The Pi's own default name is shown as it is","공간 미지정",DeviceText.roomLabel("공간 미지정"));
    }
}
