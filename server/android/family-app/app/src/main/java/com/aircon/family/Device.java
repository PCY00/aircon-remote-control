package com.aircon.family;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * One device of GET /v1/homes/&lt;home&gt;/devices (decision 0019): name, room, type, capability blocks
 * and last reported state. Built from plain maps so parsing and the derived rules run in JVM tests.
 */
final class Device {
    /** Battery sensors that have not reported for this long are shown as 응답 없음. */
    static final double STALE_SECONDS=6*3600;
    static final int LOW_BATTERY=20;
    private static final Pattern TOKEN=Pattern.compile("[a-z][a-z0-9_]{0,31}");
    private static final Pattern ID=Pattern.compile("[A-Za-z0-9_.:-]{1,64}");

    final String id, name, room, type;
    final List<String> capabilities;
    /** Values are null, Boolean, Double or String only. Insertion order is the server's order. */
    final Map<String,Object> state;
    /** Epoch seconds of the device's last report, or null when it never reported. */
    final Double reportedAt;
    final boolean controllable;

    Device(String id,String name,String room,String type,List<String> capabilities,Map<String,Object> state,Double reportedAt,boolean controllable) {
        this.id=id; this.type=type==null ? "" : type;
        this.name=name==null || name.isEmpty() ? DeviceCategory.typeLabel(this.type) : name;
        this.room=room==null ? "" : room;
        this.capabilities=Collections.unmodifiableList(new ArrayList<>(capabilities));
        this.state=Collections.unmodifiableMap(new LinkedHashMap<>(state));
        this.reportedAt=reportedAt; this.controllable=controllable;
    }

    /** Returns null for an entry without a usable id; unknown types, blocks and state keys are kept. */
    static Device from(Object raw) {
        if(!(raw instanceof Map)) return null;
        Map<String,Object> value=Plain.map(raw);
        String id=Plain.text(value.get("id"));
        if(id==null || !ID.matcher(id).matches()) return null;
        String type=Plain.text(value.get("type"),"");
        if(!TOKEN.matcher(type).matches()) type="unknown";
        List<String> capabilities=new ArrayList<>();
        for(Object item:Plain.list(value.get("capabilities"))) {
            String capability=Plain.text(item);
            if(capability!=null && TOKEN.matcher(capability).matches() && !capabilities.contains(capability) && capabilities.size()<16)
                capabilities.add(capability);
        }
        Map<String,Object> state=new LinkedHashMap<>();
        for(Map.Entry<String,Object> entry:Plain.map(value.get("state")).entrySet()) {
            if(state.size()>=16 || entry.getKey()==null || !TOKEN.matcher(entry.getKey()).matches()) continue;
            Object item=entry.getValue();
            if(item==null || item instanceof Boolean) state.put(entry.getKey(),item);
            else if(item instanceof Number) { Double number=Plain.number(item); if(number!=null) state.put(entry.getKey(),number); }
            else if(item instanceof String) state.put(entry.getKey(),Plain.clean((String)item,40));
        }
        Double reported=Plain.number(value.get("reported_at"));
        if(reported!=null && reported<=0) reported=null;
        return new Device(id,Plain.clean(Plain.text(value.get("name")),80),Plain.clean(Plain.text(value.get("room")),40),
            type,capabilities,state,reported,Plain.flag(value.get("controllable")));
    }
    static List<Device> list(Object raw) {
        List<Device> result=new ArrayList<>();List<String> seen=new ArrayList<>();
        for(Object item:Plain.list(raw)) {
            Device device=from(item);
            if(device!=null && !seen.contains(device.id)) { seen.add(device.id); result.add(device); }
        }
        return result;
    }

    String category() { return DeviceCategory.of(type); }
    boolean aircon() { return type.equals("air_conditioner"); }
    Double number(String key) { return Plain.number(state.get(key)); }
    String text(String key) { return Plain.text(state.get(key)); }
    /** TRUE/FALSE for bool or on/off/open/closed style strings, null when unknown. */
    Boolean flag(String key) {
        Object value=state.get(key);
        if(value instanceof Boolean) return (Boolean)value;
        if(value instanceof String) {
            String text=((String)value).toLowerCase(java.util.Locale.ROOT);
            if(text.equals("on") || text.equals("true") || text.equals("open") || text.equals("detected")) return true;
            if(text.equals("off") || text.equals("false") || text.equals("closed") || text.equals("clear")) return false;
        }
        if(value instanceof Double) return (Double)value!=0;
        return null;
    }
    /** Inferred power for aircons/lights/plugs: a known mode without a power key also means on. */
    Boolean power() {
        Boolean power=flag("power");
        if(power!=null) return power;
        return text("mode")!=null ? Boolean.TRUE : null;
    }
    boolean on() { return Boolean.TRUE.equals(power()); }
    /** "open", "closed" or null. */
    String contact() {
        Object value=state.get("contact");
        if("open".equals(value) || Boolean.TRUE.equals(value)) return "open";
        if("closed".equals(value) || Boolean.FALSE.equals(value)) return "closed";
        return null;
    }
    boolean hasBattery() {
        return capabilities.contains("battery") || state.containsKey("battery_percent") || state.containsKey("battery_low");
    }
    Integer batteryPercent() {
        Double percent=number("battery_percent");
        return percent==null ? null : (int)Math.round(Math.max(0,Math.min(100,percent)));
    }
    boolean batteryLow() {
        if(Boolean.TRUE.equals(state.get("battery_low"))) return true;
        Integer percent=batteryPercent();
        return percent!=null && percent<=LOW_BATTERY;
    }
    /** Only battery sensors go quiet when they stop reporting; mains devices are judged by the hub status. */
    boolean stale(double now) { return hasBattery() && reportedAt!=null && now-reportedAt>STALE_SECONDS; }
    /** "거실 에어컨" in room "거실" → "에어컨"; a name that is only the room stays as it is. */
    /** "거실 에어컨" in 거실 shows as "에어컨"; a word that merely begins with the room ("현관문" in 현관) stays whole. */
    String shortName() {
        if(room.isEmpty() || !name.startsWith(room+" ")) return name;
        String rest=name.substring(room.length()).trim();
        return rest.isEmpty() ? name : rest;
    }
}
