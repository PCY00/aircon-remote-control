package com.aircon.family;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import org.junit.Test;
import static com.aircon.family.TestMaps.*;
import static org.junit.Assert.*;

public class TimelineTest {
    private static final ZoneId SEOUL=ZoneId.of("Asia/Seoul");
    /** 2026-10-16 15:00 in Seoul. */
    private static final double NOW=ZonedDateTime.of(2026,10,16,15,0,0,0,SEOUL).toEpochSecond();
    private static final Map<String,String> NAMES=Map.of(DOOR,"현관문",CLIMATE,"거실 온습도");
    private static AppEvent door(long id,double at,String state,String device) {
        return event(id,"sensor.door_changed",at,device==null ? map("state",state) : map("state",state,"device_id",device));
    }

    @Test public void dayHeadersAreTodayYesterdayOrTheDate() {
        assertEquals("오늘",Timeline.dayLabel(NOW-3600,NOW,SEOUL));
        assertEquals("오늘",Timeline.dayLabel(NOW-15*3600,NOW,SEOUL));
        assertEquals("어제",Timeline.dayLabel(NOW-15*3600-1,NOW,SEOUL));
        assertEquals("10월 14일",Timeline.dayLabel(NOW-2*86400,NOW,SEOUL));
        assertEquals("2025년 12월 31일",Timeline.dayLabel(ZonedDateTime.of(2025,12,31,9,0,0,0,SEOUL).toEpochSecond(),NOW,SEOUL));
        assertEquals("시각 정보 없음",Timeline.dayLabel(0,NOW,SEOUL));
        assertEquals("14:05",Timeline.clock(NOW-55*60,SEOUL));
    }
    @Test public void consecutiveRecordsOfOneDeviceAndKindCollapseWithinADay() {
        List<AppEvent> events=List.of(
            door(9,NOW-60,"closed",DOOR),door(8,NOW-120,"open",DOOR),door(7,NOW-600,"closed",DOOR),
            event(6,"sensor.climate_report",NOW-700,map("temperature_c",25.1,"humidity_percent",48,"device_id",CLIMATE)),
            door(5,NOW-800,"open",DOOR),
            door(4,NOW-16*3600,"closed",DOOR),door(3,NOW-16*3600-60,"open",DOOR));
        List<Timeline.Day> days=Timeline.build(events,NAMES,SEOUL,NOW);
        assertEquals(2,days.size());
        assertEquals("오늘",days.get(0).label);assertEquals("어제",days.get(1).label);
        List<Timeline.Row> today=days.get(0).rows;
        assertEquals(3,today.size());
        assertEquals(3,today.get(0).count());
        assertEquals("현관문 열림·닫힘 3번",Timeline.title(today.get(0),NAMES));
        assertEquals("14:50–14:59",Timeline.time(today.get(0),SEOUL));
        assertEquals("거실 온습도 · 25.1° · 48%",Timeline.title(today.get(1),NAMES));
        assertEquals("A different record in between starts a new row","현관문 열림",Timeline.title(today.get(2),NAMES));
        assertEquals("The day boundary splits runs",2,days.get(1).rows.get(0).count());
    }
    @Test public void differentDevicesOfTheSameKindDoNotCollapse() {
        String window="cccccccccccccccccccccccccccccccc";
        List<Timeline.Day> days=Timeline.build(List.of(door(2,NOW-60,"open",DOOR),door(1,NOW-120,"open",window)),NAMES,SEOUL,NOW);
        assertEquals(2,days.get(0).rows.size());
        assertEquals("Unknown ids fall back to the generic title","문 열림",Timeline.title(days.get(0).rows.get(1),NAMES));
    }
    @Test public void olderRecordsKeepTheirGenericTitles() {
        assertEquals("문 닫힘",Timeline.title(door(1,NOW,"closed",null),null));
        assertEquals("온습도 측정 · 25.1° · 48%",Timeline.title(event(1,"sensor.climate_report",NOW,map("temperature_c",25.1,"humidity_percent",48)),null));
        assertEquals("기기 연결 시험",Timeline.title(event(1,"hub.connection_test",NOW,map()),null));
        assertEquals("자동화 경고 발생",Timeline.title(event(1,"automation.warning_triggered",NOW,map()),null));
        assertEquals("자동화 경고 해제",Timeline.title(event(1,"automation.warning_resolved",NOW,map()),null));
        assertEquals("문 열림",Timeline.title(event(1,"sensor.open",NOW,map()),null));
        assertEquals("현관 움직임 감지",Timeline.title(event(1,"sensor.motion_detected",NOW,map()),"현관"));
        assertEquals("누수 감지",Timeline.title(event(1,"sensor.leak_detected",NOW,map()),null));
        assertEquals("가족 활동",Timeline.title(event(1,"family.control",NOW,map()),null));
        assertEquals("집의 새 기록",Timeline.title(event(1,"something.else",NOW,map()),null));
    }
    @Test public void collapsedTitlesForSingleStatesClimateAndWarnings() {
        List<Timeline.Day> doors=Timeline.build(List.of(door(2,NOW-60,"open",null),door(1,NOW-90,"open",null)),NAMES,SEOUL,NOW);
        assertEquals("문 열림 2번",Timeline.title(doors.get(0).rows.get(0),NAMES));
        List<Timeline.Day> climate=Timeline.build(List.of(event(2,"sensor.climate_report",NOW-60,map("device_id",CLIMATE)),
            event(1,"sensor.climate_report",NOW-120,map("device_id",CLIMATE))),NAMES,SEOUL,NOW);
        assertEquals("거실 온습도 측정 2번",Timeline.title(climate.get(0).rows.get(0),NAMES));
        List<Timeline.Day> warnings=Timeline.build(List.of(event(2,"automation.warning_resolved",NOW-60,map()),
            event(1,"automation.warning_triggered",NOW-120,map())),NAMES,SEOUL,NOW);
        assertEquals("자동화 경고 발생·해제 2번",Timeline.title(warnings.get(0).rows.get(0),NAMES));
        assertNotEquals(doors.get(0).rows.get(0).key(),climate.get(0).rows.get(0).key());
    }
    @Test public void recordsBelongToADeviceByIdOrByKindWhenOlder() {
        Device door=TestMaps.door("closed",null,null), climate=TestMaps.climate(25.0,50.0,null);
        assertTrue(Timeline.belongsTo(door(1,NOW,"open",DOOR),door));
        assertFalse(Timeline.belongsTo(door(1,NOW,"open","cccccccccccccccccccccccccccccccc"),door));
        assertTrue(Timeline.belongsTo(door(1,NOW,"open",null),door));
        assertFalse(Timeline.belongsTo(door(1,NOW,"open",null),climate));
        assertTrue(Timeline.belongsTo(event(1,"sensor.climate_report",NOW,map()),climate));
        assertFalse(Timeline.belongsTo(event(1,"hub.connection_test",NOW,map()),aircon(map())));
    }
}
