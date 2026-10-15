package com.aircon.family;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.Test;
import static com.aircon.family.AlertLevels.*;
import static org.junit.Assert.*;

public class AlertLevelsTest {
    @Test public void eventKindsMapToTheContractCategories() {
        assertEquals(SAFETY,categoryOf("safety.gas"));assertEquals(SAFETY,categoryOf("sensor.leak_detected"));assertEquals(SAFETY,categoryOf("sensor.smoke_detected"));
        for(String kind:new String[]{"sensor.door_changed","sensor.open","sensor.closed","sensor.motion_detected"}) assertEquals(kind,SECURITY,categoryOf(kind));
        assertEquals(DEVICE,categoryOf("device.battery_low"));
        assertEquals(ENVIRONMENT,categoryOf("environment.too_hot"));assertEquals(ENVIRONMENT,categoryOf("sensor.climate_threshold"));
        assertEquals(REPORT,categoryOf("sensor.climate_report"));
        assertEquals(AUTOMATION,categoryOf("automation.warning_triggered"));assertEquals(AUTOMATION,categoryOf("automation.ran"));
        assertEquals(FAMILY,categoryOf("family.control"));
        assertEquals(OTHER,categoryOf("hub.connection_test"));assertEquals(OTHER,categoryOf("sensor.unknown"));assertEquals(OTHER,categoryOf(null));
    }
    @Test public void legacyFcmCategoriesMapToAlertCategories() {
        assertEquals(SECURITY,fromLegacy("door"));assertEquals(REPORT,fromLegacy("climate"));
        assertEquals(AUTOMATION,fromLegacy("warning"));assertEquals(OTHER,fromLegacy("other"));assertEquals(OTHER,fromLegacy(null));
        assertEquals("alert_category wins over the legacy value",SAFETY,incomingCategory("safety","other"));
        assertEquals(SECURITY,incomingCategory(null,"door"));assertEquals(REPORT,incomingCategory("","climate"));
        assertEquals("Unknown new categories are shown as other",OTHER,incomingCategory("weather","door"));
    }
    @Test public void safetyCannotBeSilencedAndOtherIsNotConfigurable() {
        assertEquals(List.of(URGENT,ALERT),Arrays.asList(allowed(SAFETY)));
        for(String category:new String[]{SECURITY,DEVICE,ENVIRONMENT,REPORT,AUTOMATION,FAMILY})
            assertEquals(category,List.of(URGENT,ALERT,QUIET,OFF),Arrays.asList(allowed(category)));
        assertEquals(0,allowed(OTHER).length);assertFalse(configurable(OTHER));
        assertFalse(valid(SAFETY,QUIET));assertFalse(valid(SAFETY,OFF));assertTrue(valid(REPORT,OFF));assertFalse(valid(SECURITY,"loud"));
        assertEquals(7,CATEGORIES.length);
    }
    @Test public void defaultsFollowTheContract() {
        Map<String,String> levels=defaults();
        assertEquals(URGENT,levels.get(SAFETY));assertEquals(ALERT,levels.get(SECURITY));assertEquals(ALERT,levels.get(DEVICE));
        assertEquals(QUIET,levels.get(ENVIRONMENT));assertEquals(OFF,levels.get(REPORT));assertEquals(ALERT,levels.get(AUTOMATION));
        assertEquals(QUIET,levels.get(FAMILY));assertEquals(7,levels.size());
    }
    @Test public void oldSwitchesMigrateToAlertOrOff() {
        Map<String,String> levels=migrate(false,true,false);
        assertEquals(OFF,levels.get(SECURITY));assertEquals(ALERT,levels.get(REPORT));assertEquals(OFF,levels.get(AUTOMATION));
        assertEquals("Untouched categories keep their defaults",URGENT,levels.get(SAFETY));assertEquals(QUIET,levels.get(FAMILY));
        assertEquals(defaults(),migrate(true,false,true));
    }
    @Test public void levelsFoldIntoTheLegacyPreferencesBody() {
        Map<String,String> levels=defaults();
        assertEquals(Map.of("door",true,"climate",false,"warning",true),legacy(levels));
        levels.put(SECURITY,QUIET);levels.put(REPORT,URGENT);levels.put(AUTOMATION,OFF);
        assertEquals(Map.of("door",false,"climate",true,"warning",false),legacy(levels));
        assertTrue(reportIntervalVisible(ALERT));assertTrue(reportIntervalVisible(URGENT));assertFalse(reportIntervalVisible(QUIET));
        assertTrue(validInterval(15));assertFalse(validInterval(10));
    }
    @Test public void quietHoursHandleRangesCrossingMidnight() {
        int start=23*60, end=7*60;
        assertTrue(inQuietHours(start,end,23*60));assertTrue(inQuietHours(start,end,2*60));assertTrue(inQuietHours(start,end,7*60-1));
        assertFalse(inQuietHours(start,end,7*60));assertFalse(inQuietHours(start,end,12*60));assertFalse(inQuietHours(start,end,23*60-1));
        assertTrue(inQuietHours(13*60,14*60,13*60+30));assertFalse(inQuietHours(13*60,14*60,14*60));assertFalse(inQuietHours(13*60,14*60,12*60));
        assertFalse("An empty range is never quiet",inQuietHours(600,600,600));
        assertEquals(23*60,QUIET_START);assertEquals(7*60,QUIET_END);
    }
    @Test public void channelChoiceAndLocalDrop() {
        assertEquals(CHANNEL_URGENT,channel(SAFETY,URGENT,true));assertEquals(CHANNEL_URGENT,channel(REPORT,URGENT,false));
        assertEquals(CHANNEL_REPORT,channel(REPORT,ALERT,false));assertEquals(CHANNEL_REPORT,channel(REPORT,ALERT,true));
        assertEquals(CHANNEL_QUIET,channel(SECURITY,ALERT,true));assertEquals(CHANNEL_EVENTS,channel(SECURITY,ALERT,false));
        assertEquals(CHANNEL_EVENTS,channel(OTHER,ALERT,false));
        assertEquals("family_events",CHANNEL_EVENTS);assertEquals("family_climate",CHANNEL_REPORT);
        assertTrue(display(SECURITY,ALERT,false));assertTrue(display(SECURITY,URGENT,false));
        assertFalse(display(SECURITY,QUIET,false));assertFalse(display(REPORT,OFF,false));
        assertTrue("Tests always show",display(REPORT,OFF,true));assertTrue("Other always shows",display(OTHER,null,false));
        assertTrue(showsInAll(SECURITY,QUIET));assertFalse(showsInAll(SECURITY,OFF));assertTrue(showsInAll(OTHER,null));
    }
    @Test public void notificationTextIsGenericAndIdsDoNotCollide() {
        assertEquals("시험 알림이 도착했어요.",body(OTHER,true));
        assertEquals("새 기록이 도착했어요. 앱에서 확인해 주세요.",body(OTHER,false));
        for(String category:FILTERS){ assertFalse(body(category,false).isEmpty()); assertTrue(title(category).startsWith("우리 집")); }
        assertEquals("우리 집 · 보안",title(SECURITY));assertEquals("family_security",group(SECURITY));
        assertEquals(100,summaryId(SAFETY));assertEquals(107,summaryId(OTHER));
        for(String id:new String[]{"12345678-1234-1234-1234-123456789abc","00000000-0000-0000-0000-000000000000",null})
            assertTrue(notificationId(id)>=1000);
        assertEquals(notificationId("a"),notificationId("a"));
        assertEquals("긴급",levelLabel(URGENT));assertEquals("끔",levelLabel(OFF));assertEquals("정기 보고",label(REPORT));
        assertEquals("누수·연기",caption(SAFETY));
    }
}
