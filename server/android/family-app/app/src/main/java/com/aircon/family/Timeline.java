package com.aircon.family;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * The 알림 tab's record list: day headers (오늘 / 어제 / M월 d일) and rows where consecutive records of the
 * same device and kind within a day collapse into one ("현관문 열림·닫힘 6번"). Titles use the device name
 * from payload.device_id and fall back to the generic titles of older records.
 */
final class Timeline {
    private Timeline() {}

    static final class Row {
        /** Newest first; a single record when nothing collapsed. */
        final List<AppEvent> events;
        Row(List<AppEvent> events) { this.events=Collections.unmodifiableList(events); }
        AppEvent newest() { return events.get(0); }
        AppEvent oldest() { return events.get(events.size()-1); }
        int count() { return events.size(); }
        /** Stable within a load, for remembering which rows are expanded. */
        String key() { return newest().id+":"+newest().kind+":"+count(); }
    }
    static final class Day {
        final String label;
        final List<Row> rows;
        Day(String label,List<Row> rows) { this.label=label; this.rows=rows; }
    }

    static List<Day> build(List<AppEvent> events,Map<String,String> names,ZoneId zone,double now) {
        List<Day> days=new ArrayList<>();
        LocalDate currentDay=null; Day day=null; List<AppEvent> run=null;
        for(AppEvent event:events) {
            LocalDate date=date(event.receivedAt,zone);
            if(day==null || !date.equals(currentDay)) {
                if(run!=null) day.rows.add(new Row(run));
                run=null; currentDay=date; day=new Day(dayLabel(event.receivedAt,now,zone),new ArrayList<>()); days.add(day);
            }
            if(run!=null && sameRun(run.get(0),event)) run.add(event);
            else { if(run!=null) day.rows.add(new Row(run)); run=new ArrayList<>(); run.add(event); }
        }
        if(run!=null) day.rows.add(new Row(run));
        return days;
    }
    static LocalDate date(double seconds,ZoneId zone) {
        return Instant.ofEpochMilli((long)(seconds*1000)).atZone(zone).toLocalDate();
    }
    static String dayLabel(double seconds,double now,ZoneId zone) {
        if(seconds<=0) return "시각 정보 없음";
        LocalDate date=date(seconds,zone), today=date(now,zone);
        if(date.equals(today)) return "오늘";
        if(date.equals(today.minusDays(1))) return "어제";
        if(date.getYear()!=today.getYear()) return date.getYear()+"년 "+date.getMonthValue()+"월 "+date.getDayOfMonth()+"일";
        return date.getMonthValue()+"월 "+date.getDayOfMonth()+"일";
    }
    static String clock(double seconds,ZoneId zone) {
        if(seconds<=0) return "";
        ZonedDateTime time=Instant.ofEpochMilli((long)(seconds*1000)).atZone(zone);
        return String.format(java.util.Locale.ROOT,"%02d:%02d",time.getHour(),time.getMinute());
    }
    /** Door open/close records are one family; warning triggered/resolved are another. */
    static String family(AppEvent event) {
        if(event.door()) return "door";
        if(event.kind.startsWith("automation.warning_")) return "automation.warning";
        return event.kind;
    }
    static boolean sameRun(AppEvent a,AppEvent b) {
        String x=a.deviceId==null ? "" : a.deviceId, y=b.deviceId==null ? "" : b.deviceId;
        return x.equals(y) && family(a).equals(family(b));
    }
    /** A record belongs to a device by payload.device_id; older records without it match by kind. */
    static boolean belongsTo(AppEvent event,Device device) {
        if(event.deviceId!=null) return event.deviceId.equals(device.id);
        switch(device.type) {
            case "door_sensor": return event.door();
            case "climate_sensor": return event.climate();
            case "motion_sensor": return event.kind.equals("sensor.motion_detected");
            case "leak_sensor": return event.kind.equals("sensor.leak_detected");
            case "smoke_sensor": return event.kind.equals("sensor.smoke_detected");
            default: return false;
        }
    }
    static String name(AppEvent event,Map<String,String> names) {
        return event.deviceId==null || names==null ? null : names.get(event.deviceId);
    }
    static String title(AppEvent event,String name) {
        String kind=event.kind;
        if(kind.equals("hub.connection_test")) return "기기 연결 시험";
        if(event.door()) {
            String state="open".equals(event.doorState()) ? "열림" : "닫힘";
            return (name==null ? "문" : name)+" "+state;
        }
        if(event.climate()) {
            String values=DeviceText.climate(event.number("temperature_c"),event.number("humidity_percent"));
            String base=name==null ? "온습도 측정" : name;
            return values==null ? base : base+" · "+values;
        }
        if(kind.equals("sensor.motion_detected")) return name==null ? "움직임 감지" : name+" 움직임 감지";
        if(kind.equals("sensor.leak_detected")) return name==null ? "누수 감지" : name+" 누수 감지";
        if(kind.equals("sensor.smoke_detected")) return name==null ? "연기 감지" : name+" 연기 감지";
        if(kind.equals("sensor.climate_threshold")) return name==null ? "온습도 기준 알림" : name+" 온습도 기준 알림";
        if(kind.equals("automation.warning_triggered")) return "자동화 경고 발생";
        if(kind.equals("automation.warning_resolved")) return "자동화 경고 해제";
        if(kind.startsWith("automation.")) return "자동화 실행";
        if(kind.startsWith("device.")) return name==null ? "기기 알림" : name+" 기기 알림";
        if(kind.startsWith("family.")) return "가족 활동";
        if(kind.startsWith("safety.")) return name==null ? "안전 알림" : name+" 안전 알림";
        if(kind.startsWith("environment.")) return name==null ? "환경 알림" : name+" 환경 알림";
        return "집의 새 기록";
    }
    /** "현관문 열림·닫힘 6번", "거실 온습도 측정 12번", or the single record's title. */
    static String title(Row row,Map<String,String> names) {
        AppEvent first=row.newest(); String name=name(first,names);
        if(row.count()==1) return title(first,name);
        if(first.door()) {
            boolean open=false, closed=false;
            for(AppEvent event:row.events) { if("open".equals(event.doorState())) open=true; else closed=true; }
            String states=open && closed ? "열림·닫힘" : open ? "열림" : "닫힘";
            return (name==null ? "문" : name)+" "+states+" "+row.count()+"번";
        }
        if(first.climate()) return (name==null ? "온습도" : name)+" 측정 "+row.count()+"번";
        if(family(first).equals("automation.warning")) {
            boolean triggered=false, resolved=false;
            for(AppEvent event:row.events) { if(event.kind.endsWith("triggered")) triggered=true; else resolved=true; }
            return "자동화 경고 "+(triggered && resolved ? "발생·해제" : triggered ? "발생" : "해제")+" "+row.count()+"번";
        }
        return title(first,name)+" "+row.count()+"번";
    }
    /** "14:05" for one record, "13:10–14:05" for a collapsed row. */
    static String time(Row row,ZoneId zone) {
        String newest=clock(row.newest().receivedAt,zone);
        if(row.count()==1) return newest;
        return clock(row.oldest().receivedAt,zone)+"–"+newest;
    }
    static String icon(String alertCategory) {
        switch(alertCategory) {
            case AlertLevels.SAFETY: return "droplet";
            case AlertLevels.SECURITY: return "door";
            case AlertLevels.DEVICE: return "hub";
            case AlertLevels.ENVIRONMENT: return "thermometer";
            case AlertLevels.REPORT: return "thermometer";
            case AlertLevels.AUTOMATION: return "warning";
            case AlertLevels.FAMILY: return "family";
            default: return "hub";
        }
    }
}
