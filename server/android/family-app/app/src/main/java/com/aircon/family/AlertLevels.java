package com.aircon.family;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Alert categories × levels from decision 0019. Plain Java so every mapping, the quiet-hours range
 * and the channel choice run in JVM tests. The server sends only urgent/alert; quiet/off stay in the record.
 */
final class AlertLevels {
    private AlertLevels() {}

    static final String SAFETY="safety", SECURITY="security", DEVICE="device", ENVIRONMENT="environment",
        REPORT="report", AUTOMATION="automation", FAMILY="family", OTHER="other";
    /** The seven categories a phone chooses a level for, in settings order. */
    static final String[] CATEGORIES={SAFETY,SECURITY,DEVICE,ENVIRONMENT,REPORT,AUTOMATION,FAMILY};
    /** Filter chip order in the 알림 tab. */
    static final String[] FILTERS={SAFETY,SECURITY,DEVICE,ENVIRONMENT,REPORT,AUTOMATION,FAMILY,OTHER};
    static final String URGENT="urgent", ALERT="alert", QUIET="quiet", OFF="off";
    static final String[] LEVELS={URGENT,ALERT,QUIET,OFF};
    static final int[] INTERVALS={1,5,15,60};
    /** Default do-not-disturb range in minutes of the day: 23:00–07:00. */
    static final int QUIET_START=23*60, QUIET_END=7*60;
    static final String CHANNEL_EVENTS="family_events", CHANNEL_REPORT="family_climate",
        CHANNEL_URGENT="family_urgent", CHANNEL_QUIET="family_quiet";

    static String label(String category) {
        switch(category) {
            case SAFETY: return "안전";
            case SECURITY: return "보안";
            case DEVICE: return "기기";
            case ENVIRONMENT: return "환경";
            case REPORT: return "정기 보고";
            case AUTOMATION: return "자동화";
            case FAMILY: return "가족";
            default: return "기타";
        }
    }
    /** What each category covers, shown under its name in settings. */
    static String caption(String category) {
        switch(category) {
            case SAFETY: return "누수·연기";
            case SECURITY: return "문·움직임";
            case DEVICE: return "조작 실패·응답 없음·배터리";
            case ENVIRONMENT: return "온습도 기준";
            case REPORT: return "온습도 값";
            case AUTOMATION: return "자동화 실행·경고";
            case FAMILY: return "누가 조작함";
            default: return "연결 시험 등";
        }
    }
    static String levelLabel(String level) {
        switch(level) {
            case URGENT: return "긴급";
            case ALERT: return "알림";
            case QUIET: return "조용히";
            default: return "끔";
        }
    }
    static String levelMeaning(String level) {
        switch(level) {
            case URGENT: return "방해 금지 시간에도 소리로 알려요";
            case ALERT: return "소리로 알려요. 방해 금지 시간엔 조용히 보여요";
            case QUIET: return "휴대폰 알림 없이 알림 탭에만 남겨요";
            default: return "알림 탭의 ‘전체’에서도 숨겨요";
        }
    }
    static String defaultLevel(String category) {
        switch(category) {
            case SAFETY: return URGENT;
            case SECURITY: case DEVICE: case AUTOMATION: return ALERT;
            case ENVIRONMENT: case FAMILY: return QUIET;
            case REPORT: return OFF;
            default: return ALERT;
        }
    }
    static Map<String,String> defaults() {
        Map<String,String> levels=new LinkedHashMap<>();
        for(String category:CATEGORIES) levels.put(category,defaultLevel(category));
        return levels;
    }
    /** Safety can never be silenced; the other categories take all four levels; other is not configurable. */
    static String[] allowed(String category) {
        if(SAFETY.equals(category)) return new String[]{URGENT,ALERT};
        for(String known:CATEGORIES) if(known.equals(category)) return LEVELS.clone();
        return new String[0];
    }
    static boolean valid(String category,String level) {
        for(String value:allowed(category)) if(value.equals(level)) return true;
        return false;
    }
    static boolean configurable(String category) { return allowed(category).length>0; }
    static boolean validInterval(int minutes) {
        for(int value:INTERVALS) if(value==minutes) return true;
        return false;
    }

    /** Event kind → alert category, exactly as the contract's table (unknown kinds are other). */
    static String categoryOf(String kind) {
        String k=kind==null ? "" : kind;
        if(k.startsWith("safety.") || k.equals("sensor.leak_detected") || k.equals("sensor.smoke_detected")) return SAFETY;
        if(k.equals("sensor.door_changed") || k.equals("sensor.open") || k.equals("sensor.closed") || k.equals("sensor.motion_detected")) return SECURITY;
        if(k.startsWith("device.")) return DEVICE;
        if(k.startsWith("environment.") || k.equals("sensor.climate_threshold")) return ENVIRONMENT;
        if(k.equals("sensor.climate_report")) return REPORT;
        if(k.startsWith("automation.")) return AUTOMATION;
        if(k.startsWith("family.")) return FAMILY;
        return OTHER;
    }
    /** Legacy FCM category (door/climate/warning/other) → alert category. */
    static String fromLegacy(String legacy) {
        if("door".equals(legacy)) return SECURITY;
        if("climate".equals(legacy)) return REPORT;
        if("warning".equals(legacy)) return AUTOMATION;
        return OTHER;
    }
    /** FCM data from a 0.7 server carries alert_category; an older server only the legacy category. */
    static String incomingCategory(String alertCategory,String legacy) {
        if(alertCategory!=null && !alertCategory.isEmpty()) {
            for(String known:FILTERS) if(known.equals(alertCategory)) return known;
            return OTHER;
        }
        return fromLegacy(legacy);
    }

    /** One-time move of the 0.6 door/climate/warning switches: on → 알림, off → 끔; the rest keep their defaults. */
    static Map<String,String> migrate(boolean door,boolean climate,boolean warning) {
        Map<String,String> levels=defaults();
        levels.put(SECURITY,door ? ALERT : OFF);
        levels.put(REPORT,climate ? ALERT : OFF);
        levels.put(AUTOMATION,warning ? ALERT : OFF);
        return levels;
    }
    /** Body of the legacy /preferences call for a server without /notification-levels. */
    static Map<String,Boolean> legacy(Map<String,String> levels) {
        Map<String,Boolean> result=new LinkedHashMap<>();
        result.put("door",delivers(levels.get(SECURITY)));
        result.put("climate",delivers(levels.get(REPORT)));
        result.put("warning",delivers(levels.get(AUTOMATION)));
        return result;
    }
    /** The server pushes only these two levels to the phone. */
    static boolean delivers(String level) { return URGENT.equals(level) || ALERT.equals(level); }
    /** 정기 보고 간격 matters only while reports reach the phone. */
    static boolean reportIntervalVisible(String reportLevel) { return delivers(reportLevel); }
    /** 끔 hides a category from the 알림 tab's 전체 list; its own chip still shows it. */
    static boolean showsInAll(String category,String level) { return !configurable(category) || !OFF.equals(level); }
    /** A push that arrives anyway (older server, a race with a level change) is dropped unless this phone wants it. */
    static boolean display(String category,String localLevel,boolean test) {
        return test || !configurable(category) || delivers(localLevel);
    }

    /** Minutes of the day; start == end means no quiet range. Ranges may cross midnight (23:00–07:00). */
    static boolean inQuietHours(int start,int end,int now) {
        if(start==end) return false;
        if(start<end) return now>=start && now<end;
        return now>=start || now<end;
    }
    /** 긴급 always rings; 정기 보고 keeps the existing low channel; 알림 goes quiet during do-not-disturb hours. */
    static String channel(String category,String level,boolean quietHours) {
        if(URGENT.equals(level)) return CHANNEL_URGENT;
        if(REPORT.equals(category)) return CHANNEL_REPORT;
        return quietHours ? CHANNEL_QUIET : CHANNEL_EVENTS;
    }
    static String title(String category) { return OTHER.equals(category) ? "우리 집 알림" : "우리 집 · "+label(category); }
    /** Generic per-category text: FCM never carries device names or values; details are read in the app. */
    static String body(String category,boolean test) {
        if(test) return "시험 알림이 도착했어요.";
        switch(category) {
            case SAFETY: return "안전 알림이 왔어요. 앱에서 바로 확인해 주세요.";
            case SECURITY: return "문이나 움직임에 변화가 있어요. 앱에서 확인해 주세요.";
            case DEVICE: return "기기 상태를 확인해 주세요.";
            case ENVIRONMENT: return "온습도가 기준을 넘었어요. 앱에서 확인해 주세요.";
            case REPORT: return "새 온습도 측정값이 도착했어요.";
            case AUTOMATION: return "자동화 소식이 있어요. 앱에서 확인해 주세요.";
            case FAMILY: return "가족이 기기를 조작했어요.";
            default: return "새 기록이 도착했어요. 앱에서 확인해 주세요.";
        }
    }
    /** Notifications of one category share a group so they stack; each message keeps its own id. */
    static String group(String category) { return "family_"+category; }
    static int summaryId(String category) {
        for(int i=0;i<FILTERS.length;i++) if(FILTERS[i].equals(category)) return 100+i;
        return 100+FILTERS.length;
    }
    /** Stable per message, never one of the summary ids (100–108). */
    static int notificationId(String messageId) {
        return 1000+((messageId==null ? 0 : messageId.hashCode()) & 0x3fffffff);
    }
}
