package com.aircon.family;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** One record of GET /v1/homes/&lt;home&gt;/events as plain values; payload.device_id links it to a {@link Device}. */
final class AppEvent {
    final long id;
    final String kind;
    /** Epoch seconds the server received it; 0 when missing. */
    final double receivedAt;
    final Map<String,Object> payload;
    /** payload.device_id (0.7 Pi agent); null on older records. */
    final String deviceId;

    AppEvent(long id,String kind,double receivedAt,Map<String,Object> payload) {
        this.id=id; this.kind=kind==null ? "" : kind; this.receivedAt=receivedAt;
        this.payload=Collections.unmodifiableMap(new LinkedHashMap<>(payload));
        String device=Plain.text(payload.get("device_id"));
        this.deviceId=device==null || device.isEmpty() ? null : device;
    }
    static AppEvent from(Object raw) {
        if(!(raw instanceof Map)) return null;
        Map<String,Object> value=Plain.map(raw);
        String kind=Plain.text(value.get("kind"));
        if(kind==null || kind.isEmpty()) return null;
        Double id=Plain.number(value.get("id")), received=Plain.number(value.get("received_at"));
        return new AppEvent(id==null ? 0 : id.longValue(),kind,received==null || received<0 ? 0 : received,Plain.map(value.get("payload")));
    }
    /** Newest first, whatever order the server used. */
    static List<AppEvent> list(Object raw) {
        List<AppEvent> result=new ArrayList<>();
        for(Object item:Plain.list(raw)) { AppEvent event=from(item); if(event!=null) result.add(event); }
        result.sort((a,b)->a.receivedAt!=b.receivedAt ? Double.compare(b.receivedAt,a.receivedAt) : Long.compare(b.id,a.id));
        return result;
    }
    String text(String key) { return Plain.text(payload.get(key)); }
    Double number(String key) { return Plain.number(payload.get(key)); }
    String alertCategory() { return AlertLevels.categoryOf(kind); }
    boolean door() { return kind.equals("sensor.door_changed") || kind.equals("sensor.open") || kind.equals("sensor.closed"); }
    /** "open"/"closed" for door records (the kind decides for sensor.open/closed). */
    String doorState() {
        if(kind.equals("sensor.open")) return "open";
        if(kind.equals("sensor.closed")) return "closed";
        String state=text("state");
        return "open".equals(state) ? "open" : "closed".equals(state) ? "closed" : null;
    }
    boolean climate() { return kind.equals("sensor.climate_report"); }
}
