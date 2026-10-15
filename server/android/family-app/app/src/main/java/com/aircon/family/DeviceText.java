package com.aircon.family;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Short Korean texts for tiles, chips and room headers. Pure so the wording is unit-tested. */
final class DeviceText {
    private DeviceText() {}

    static final String NO_ROOM="공간 미지정", NO_RESPONSE="응답 없음", UNKNOWN="상태 모름";

    /** 24 → "24", 25.14 → "25.1". */
    static String number(double value) {
        double rounded=Math.round(value*10)/10.0;
        if(Math.abs(rounded-Math.rint(rounded))<1e-9) return String.valueOf((long)Math.rint(rounded));
        return String.format(Locale.ROOT,"%.1f",rounded);
    }
    /** Seconds → "N분", "N시간", "N일" (at least one minute). */
    static String duration(double seconds) {
        long minutes=Math.max(1,(long)Math.floor(Math.max(0,seconds)/60));
        if(minutes<60) return minutes+"분";
        long hours=minutes/60;
        if(hours<24) return hours+"시간";
        return (hours/24)+"일";
    }
    /** Elapsed seconds → "방금", "3분 전", "2시간 전", "4일 전". */
    static String ago(double seconds) {
        if(seconds<60) return "방금";
        return duration(seconds)+" 전";
    }
    /** Subject particle: "현관문" → "현관문이", "문 센서" → "문 센서가". */
    static String subject(String word) {
        if(word==null || word.isEmpty()) return "";
        char last=word.charAt(word.length()-1);
        boolean batchim;
        if(last>=0xAC00 && last<=0xD7A3) batchim=(last-0xAC00)%28!=0;
        else if(last>='0' && last<='9') batchim="013678".indexOf(last)>=0;
        else if(Character.isLetter(last) && last<128) batchim="lmnLMN".indexOf(last)>=0; // 홀·룸·펜 이, 도어·센서 가
        else batchim=false;
        return word+(batchim ? "이" : "가");
    }
    static String climate(Double temperature,Double humidity) {
        if(temperature!=null && humidity!=null) return number(temperature)+"° · "+number(humidity)+"%";
        if(temperature!=null) return number(temperature)+"°";
        if(humidity!=null) return number(humidity)+"%";
        return null;
    }
    static String roomLabel(String room) { return room==null || room.isEmpty() ? NO_ROOM : room; }
    static String modeLabel(String mode) {
        if(mode==null) return "켜짐";
        switch(mode) {
            case "cool": return "냉방";
            case "heat": return "난방";
            case "auto": return "자동";
            case "dry": return "제습";
            case "fan": case "fan_only": return "송풍";
            default: return "켜짐";
        }
    }
    /** A state value as text: on/off for booleans, trimmed numbers, strings as they are. */
    static String value(Object value) {
        if(value==null) return "—";
        if(value instanceof Boolean) return (Boolean)value ? "켜짐" : "꺼짐";
        Double number=Plain.number(value);
        if(number!=null) return number(number);
        return value.toString();
    }
    static String aircon(Device device) {
        Boolean power=device.power();
        if(Boolean.FALSE.equals(power)) return "꺼짐";
        if(power==null) return UNKNOWN;
        String mode=device.text("mode");Double setpoint=device.number("setpoint_c");
        String label=modeLabel(mode);
        if(setpoint!=null && ("cool".equals(mode) || "heat".equals(mode))) return label+" "+number(setpoint)+"°";
        return label;
    }
    /**
     * One line under a tile: "냉방 24°", "닫힘 · 3분 전", "25.1° · 48%", "켜짐 · 70%". {@code changedAt}
     * is the latest door record of this device when known (else the report time is used).
     */
    static String summary(Device device,double now,Double changedAt) {
        switch(device.type) {
            case "air_conditioner": return aircon(device);
            case "door_sensor": {
                String contact=device.contact();
                if(contact==null) return UNKNOWN;
                String text=contact.equals("open") ? "열림" : "닫힘";
                Double since=changedAt!=null ? changedAt : device.reportedAt;
                return since==null ? text : text+" · "+ago(now-since);
            }
            case "climate_sensor": {
                String text=climate(device.number("temperature_c"),device.number("humidity_percent"));
                return text==null ? "측정값 없음" : text;
            }
            case "light": {
                Boolean power=device.power();
                if(power==null) return UNKNOWN;
                if(!power) return "꺼짐";
                Double brightness=device.number("brightness_percent");
                return brightness==null ? "켜짐" : "켜짐 · "+number(brightness)+"%";
            }
            case "plug": {
                Boolean power=device.power();
                if(power==null) return UNKNOWN;
                if(!power) return "꺼짐";
                Double watts=device.number("power_w");
                return watts==null ? "켜짐" : "켜짐 · "+number(watts)+"W";
            }
            case "motion_sensor": {
                Boolean motion=device.flag("motion");
                return motion==null ? UNKNOWN : motion ? "움직임 감지" : "움직임 없음";
            }
            case "leak_sensor": {
                Boolean leak=device.flag("leak");
                return leak==null ? UNKNOWN : leak ? "누수 감지" : "이상 없음";
            }
            case "smoke_sensor": {
                Boolean smoke=device.flag("smoke");
                return smoke==null ? UNKNOWN : smoke ? "연기 감지" : "이상 없음";
            }
            default:
                for(Object value:device.state.values()) return value(value);
                return UNKNOWN;
        }
    }
    /** The tile line, with 응답 없음 replacing a value that may be hours old. */
    static String tile(Device device,double now,Double changedAt) {
        return device.stale(now) ? NO_RESPONSE : summary(device,now,changedAt);
    }
    /** "26.2° · 52%" of the first climate sensor in a room that has values, else null. */
    static String roomClimate(List<Device> devices) {
        for(Device device:devices) if(device.type.equals("climate_sensor")) {
            String text=climate(device.number("temperature_c"),device.number("humidity_percent"));
            if(text!=null) return text;
        }
        return null;
    }
    /** Rooms in order of first appearance; the empty room is shown as 공간 미지정. */
    static Map<String,List<Device>> rooms(List<Device> devices) {
        Map<String,List<Device>> rooms=new LinkedHashMap<>();
        for(Device device:devices) {
            List<Device> list=rooms.get(device.room);
            if(list==null) { list=new ArrayList<>(); rooms.put(device.room,list); }
            list.add(device);
        }
        return rooms;
    }
    /** Chip summary per category: "냉방 24°"/"꺼짐", "문 닫힘"/"문 1개 열림", average "25.6° · 50%", "2개 켜짐". */
    static String category(String category,List<Device> devices,double now) {
        List<Device> members=DeviceCategory.members(devices,category);
        switch(category) {
            case DeviceCategory.HVAC: {
                List<Device> on=new ArrayList<>();boolean off=false;
                for(Device device:members) { Boolean power=device.power(); if(Boolean.TRUE.equals(power)) on.add(device); else if(Boolean.FALSE.equals(power)) off=true; }
                if(on.size()==1) return aircon(on.get(0));
                if(on.size()>1) return on.size()+"대 켜짐";
                return off ? "꺼짐" : UNKNOWN;
            }
            case DeviceCategory.SECURITY: {
                int doors=0, open=0, known=0; Boolean motion=null;
                for(Device device:members) {
                    if(device.type.equals("door_sensor")) { doors++; String contact=device.contact(); if(contact!=null) known++; if("open".equals(contact)) open++; }
                    else if(device.type.equals("motion_sensor")) { Boolean value=device.flag("motion"); if(value!=null) motion=Boolean.TRUE.equals(motion) || value; }
                }
                if(open>0) return "문 "+open+"개 열림";
                if(doors>0) return known>0 ? "문 닫힘" : UNKNOWN;
                if(motion!=null) return motion ? "움직임 감지" : "움직임 없음";
                return members.size()+"개";
            }
            case DeviceCategory.ENVIRONMENT: {
                double temperature=0, humidity=0; int temperatures=0, humidities=0;
                for(Device device:members) {
                    Double t=device.number("temperature_c"), h=device.number("humidity_percent");
                    if(t!=null){temperature+=t;temperatures++;}
                    if(h!=null){humidity+=h;humidities++;}
                }
                String text=climate(temperatures==0 ? null : temperature/temperatures,humidities==0 ? null : humidity/humidities);
                return text==null ? "측정값 없음" : text;
            }
            case DeviceCategory.LIGHT: case DeviceCategory.POWER: {
                int on=0;
                for(Device device:members) if(device.on()) on++;
                return on>0 ? on+"개 켜짐" : "모두 꺼짐";
            }
            case DeviceCategory.SAFETY: {
                for(Device device:members) if(Boolean.TRUE.equals(device.flag("leak"))) return "누수 감지";
                for(Device device:members) if(Boolean.TRUE.equals(device.flag("smoke"))) return "연기 감지";
                return "이상 없음";
            }
            default: return members.size()+"개";
        }
    }
}
