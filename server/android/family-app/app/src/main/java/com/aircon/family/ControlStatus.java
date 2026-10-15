package com.aircon.family;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** GET /v1/homes/&lt;home&gt;/control as plain values, for the rules that combine it with devices and events. */
final class ControlStatus {
    static final class Command {
        final String id, deviceId, action, state;
        final double createdAt, updatedAt;
        Command(String id,String deviceId,String action,String state,double createdAt,double updatedAt) {
            this.id=id; this.deviceId=deviceId; this.action=action; this.state=state; this.createdAt=createdAt; this.updatedAt=updatedAt;
        }
        /** When the command last changed state, for "N분 전". */
        double time() { return Math.max(createdAt,updatedAt); }
    }
    final boolean online, canControl;
    /** Controllable aircons as {id, name}. */
    final List<String[]> devices;
    final Command latest;

    ControlStatus(boolean online,boolean canControl,List<String[]> devices,Command latest) {
        this.online=online; this.canControl=canControl; this.devices=devices; this.latest=latest;
    }
    static ControlStatus from(Object raw) {
        Map<String,Object> value=Plain.map(raw);
        List<String[]> devices=new ArrayList<>();
        for(Object item:Plain.list(value.get("devices"))) {
            Map<String,Object> device=Plain.map(item);String id=Plain.text(device.get("id"));
            if(id!=null && !id.isEmpty()) devices.add(new String[]{id,Plain.clean(Plain.text(device.get("name"),""),80)});
        }
        Command latest=null;Map<String,Object> command=Plain.map(value.get("latest_command"));
        if(!command.isEmpty()) {
            Double created=Plain.number(command.get("created_at")), updated=Plain.number(command.get("updated_at"));
            latest=new Command(Plain.text(command.get("id"),""),Plain.text(command.get("device_id"),""),Plain.text(command.get("action"),""),
                Plain.text(command.get("state"),""),created==null ? 0 : created,updated==null ? 0 : updated);
        }
        return new ControlStatus(Plain.flag(value.get("online")),Plain.flag(value.get("can_control")),devices,latest);
    }
    String deviceName(String id) {
        for(String[] device:devices) if(device[0].equals(id)) return device[1].isEmpty() ? null : device[1];
        return null;
    }
    boolean has(String id) {
        for(String[] device:devices) if(device[0].equals(id)) return true;
        return false;
    }
    /** The latest command, only when it was for this device. */
    Command latestFor(String id) { return latest!=null && latest.deviceId.equals(id) ? latest : null; }
}
