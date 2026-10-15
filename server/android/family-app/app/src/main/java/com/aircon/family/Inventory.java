package com.aircon.family;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The home's device list. A 0.7 server sends it from the Pi (GET .../devices); an older server (404) or a
 * hub that never sent a list gets a fallback built from the aircon control list and the latest records.
 */
final class Inventory {
    /** A list the Pi has not refreshed for this long means the hub is not reporting. */
    static final double HUB_STALE_SECONDS=600;
    static final String FALLBACK_DOOR="legacy-door", FALLBACK_CLIMATE="legacy-climate";
    static final List<String> AIRCON_CAPABILITIES=Collections.unmodifiableList(Arrays.asList("power","setpoint","mode","fan","actions"));

    final List<Device> devices;
    /** When the Pi last sent the list (epoch seconds), null when it never did. */
    final Double updatedAt;
    /** Pi connection as the server sees it; null when unknown. */
    final Boolean hubOnline;
    /** True for a list rebuilt on the phone for an older server. */
    final boolean fallback;
    /** Fallback only: there are signs of a hub (aircons or records), so its offline status is worth showing. */
    private final boolean hubSeen;

    Inventory(List<Device> devices,Double updatedAt,Boolean hubOnline,boolean fallback,boolean hubSeen) {
        this.devices=Collections.unmodifiableList(new ArrayList<>(devices));
        this.updatedAt=updatedAt; this.hubOnline=hubOnline; this.fallback=fallback; this.hubSeen=hubSeen;
    }
    static Inventory from(Object raw) {
        Map<String,Object> value=Plain.map(raw);
        Object online=value.get("hub_online");
        return new Inventory(Device.list(value.get("devices")),Plain.number(value.get("updated_at")),
            online instanceof Boolean ? (Boolean)online : null,false,true);
    }
    /** A 0.7 server whose Pi never sent a list answers devices [] and updated_at null. */
    boolean neverReported() { return updatedAt==null && devices.isEmpty(); }

    /** The list the screens use: the server's when it has one, otherwise the fallback. */
    static Inventory effective(Inventory server,ControlStatus control,List<AppEvent> events) {
        if(server!=null && !server.neverReported()) return server;
        return fallback(control,events);
    }
    /**
     * Older server: the aircons of the control list (no room), plus one door and one climate sensor
     * taken from the latest door/climate records. Nothing here is invented beyond what those say.
     */
    static Inventory fallback(ControlStatus control,List<AppEvent> events) {
        List<Device> devices=new ArrayList<>();
        if(control!=null) for(String[] aircon:control.devices) {
            ControlStatus.Command latest=control.latestFor(aircon[0]);
            Map<String,Object> state=latest!=null && "sent".equals(latest.state) ? inferred(latest.action) : null;
            devices.add(new Device(aircon[0],aircon[1],"","air_conditioner",AIRCON_CAPABILITIES,
                state==null ? Collections.emptyMap() : state,null,true));
        }
        AppEvent door=null, climate=null;
        for(AppEvent event:events) {
            if(door==null && event.door() && event.doorState()!=null) door=event;
            if(climate==null && event.climate()) climate=event;
        }
        if(door!=null) {
            Map<String,Object> state=new LinkedHashMap<>();state.put("contact",door.doorState());
            devices.add(new Device(door.deviceId==null ? FALLBACK_DOOR : door.deviceId,"","","door_sensor",
                Collections.singletonList("contact"),state,door.receivedAt>0 ? door.receivedAt : null,false));
        }
        if(climate!=null) {
            Map<String,Object> state=new LinkedHashMap<>();List<String> capabilities=new ArrayList<>();
            Double temperature=climate.number("temperature_c"), humidity=climate.number("humidity_percent");
            if(temperature!=null){state.put("temperature_c",temperature);capabilities.add("temperature");}
            if(humidity!=null){state.put("humidity_percent",humidity);capabilities.add("humidity");}
            devices.add(new Device(climate.deviceId==null ? FALLBACK_CLIMATE : climate.deviceId,"","","climate_sensor",
                capabilities,state,climate.receivedAt>0 ? climate.receivedAt : null,false));
        }
        boolean seen=control!=null && (!control.devices.isEmpty() || !events.isEmpty());
        return new Inventory(devices,null,control==null ? null : control.online,true,seen);
    }
    /** What a successfully sent command tells about the aircon, marked inferred like the Pi's own guess. */
    static Map<String,Object> inferred(String action) {
        Map<String,Object> state=new LinkedHashMap<>();
        if(action==null) return null;
        if(action.equals("power_off")) state.put("power",false);
        else if(action.equals("cool_on")) { state.put("power",true);state.put("mode","cool");state.put("setpoint_c",24.0);state.put("fan","auto"); }
        else if(action.startsWith("cool_")) {
            String[] pieces=action.split("_");
            if(pieces.length!=3) return null;
            try { state.put("power",true);state.put("mode","cool");state.put("setpoint_c",(double)Integer.parseInt(pieces[1]));state.put("fan",pieces[2]); }
            catch(NumberFormatException invalid) { return null; }
        }
        else if(action.equals("mode_auto")) { state.put("power",true);state.put("mode","auto"); }
        else if(action.equals("mode_dry")) { state.put("power",true);state.put("mode","dry"); }
        else if(action.equals("mode_fan_only")) { state.put("power",true);state.put("mode","fan_only"); }
        else return null;
        state.put("inferred",true);
        return state;
    }
    /** Pi offline, or its list not refreshed for 10 minutes. A fallback list only knows the control status. */
    boolean hubProblem(double now) {
        if(fallback) return hubSeen && Boolean.FALSE.equals(hubOnline);
        return Boolean.FALSE.equals(hubOnline) || (updatedAt!=null && now-updatedAt>HUB_STALE_SECONDS);
    }
    Device find(String id) {
        if(id==null) return null;
        for(Device device:devices) if(device.id.equals(id)) return device;
        return null;
    }
    /** Device id → name, for record titles. */
    Map<String,String> names() {
        Map<String,String> names=new LinkedHashMap<>();
        for(Device device:devices) names.put(device.id,device.name);
        return names;
    }
}
