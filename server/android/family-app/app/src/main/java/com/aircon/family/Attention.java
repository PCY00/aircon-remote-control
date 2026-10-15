package com.aircon.family;

import java.util.ArrayList;
import java.util.List;

/**
 * "지금 확인할 것": things that need a look now, computed from the device list, the records and the aircon
 * control status. Battery and 응답 없음 exist only here; the server does not send them as alerts.
 */
final class Attention {
    private Attention() {}

    enum Tone { DANGER, WARNING, NEUTRAL }
    /** A failed or unconfirmed aircon command stays here this long. */
    static final double COMMAND_SECONDS=600;

    static final class Item {
        final String key, title, detail, category;
        /** The device the item is about, or null (hub, automation): those open the 알림 tab. */
        final String deviceId;
        final Tone tone;
        Item(String key,Tone tone,String title,String detail,String deviceId,String category) {
            this.key=key; this.tone=tone; this.title=title; this.detail=detail; this.deviceId=deviceId; this.category=category;
        }
    }

    static List<Item> compute(Inventory inventory,List<AppEvent> events,ControlStatus control,double now) {
        List<Item> danger=new ArrayList<>(), warning=new ArrayList<>(), neutral=new ArrayList<>();
        List<Device> devices=inventory==null ? new ArrayList<>() : inventory.devices;
        for(Device device:devices) {
            if(!device.type.equals("door_sensor") || !"open".equals(device.contact())) continue;
            Double since=openedAt(device,events);
            String detail=since==null ? "" : now-since<60 ? "방금 열렸어요" : DeviceText.duration(now-since)+"째";
            danger.add(new Item("door:"+device.id,Tone.DANGER,DeviceText.subject(device.name)+" 열려 있어요",detail,device.id,AlertLevels.SECURITY));
        }
        if(control!=null && control.latest!=null) {
            ControlStatus.Command command=control.latest;
            if(("failed".equals(command.state) || "unknown".equals(command.state)) && command.time()>0 && now-command.time()<=COMMAND_SECONDS) {
                Device device=inventory==null ? null : inventory.find(command.deviceId);
                String name=device!=null ? device.name : control.deviceName(command.deviceId);
                if(name==null) name="에어컨";
                danger.add(new Item("command:"+command.id,Tone.DANGER,name+" 명령이 전달되지 않았어요",
                    AirconUi.actionLabel(command.action)+" · "+DeviceText.ago(now-command.time()),command.deviceId,AlertLevels.DEVICE));
            }
        }
        AppEvent warningEvent=null;
        for(AppEvent event:events) if(event.kind.startsWith("automation.warning_")) { warningEvent=event; break; }
        if(warningEvent!=null && warningEvent.kind.equals("automation.warning_triggered"))
            danger.add(new Item("automation:"+warningEvent.id,Tone.DANGER,"자동화 경고가 켜져 있어요",
                warningEvent.receivedAt>0 ? DeviceText.ago(now-warningEvent.receivedAt) : "",null,AlertLevels.AUTOMATION));
        for(Device device:devices) if(device.batteryLow()) {
            Integer percent=device.batteryPercent();
            warning.add(new Item("battery:"+device.id,Tone.WARNING,device.name,percent==null ? "배터리 부족" : "배터리 "+percent+"%",device.id,AlertLevels.DEVICE));
        }
        boolean hub=inventory!=null && inventory.hubProblem(now);
        if(hub) neutral.add(new Item("hub",Tone.NEUTRAL,"Pi와 연결이 끊겼어요",
            inventory.updatedAt==null ? "" : "마지막 연결 "+DeviceText.ago(now-inventory.updatedAt),null,AlertLevels.DEVICE));
        // With the hub down every battery sensor goes quiet together; the hub item already says why.
        if(!hub) for(Device device:devices) if(device.stale(now))
            neutral.add(new Item("stale:"+device.id,Tone.NEUTRAL,device.name,DeviceText.NO_RESPONSE+" · "+DeviceText.duration(now-device.reportedAt),device.id,AlertLevels.DEVICE));
        List<Item> items=new ArrayList<>(danger);items.addAll(warning);items.addAll(neutral);
        return items;
    }
    /** When the door opened: its latest door record if that says open, else the device's report time. */
    static Double openedAt(Device device,List<AppEvent> events) {
        for(AppEvent event:events) {
            if(!event.door() || !Timeline.belongsTo(event,device)) continue;
            if("open".equals(event.doorState()) && event.receivedAt>0) return event.receivedAt;
            break;
        }
        return device.reportedAt;
    }
    /** The latest door record time of a door, for "닫힘 · 3분 전"; null when there is none. */
    static Double changedAt(Device device,List<AppEvent> events) {
        if(!device.type.equals("door_sensor")) return null;
        for(AppEvent event:events) if(event.door() && Timeline.belongsTo(event,device) && event.receivedAt>0) return event.receivedAt;
        return null;
    }
    static List<Item> filter(List<Item> items,String category) {
        if(category==null || category.equals("all")) return items;
        List<Item> result=new ArrayList<>();
        for(Item item:items) if(item.category.equals(category)) result.add(item);
        return result;
    }
}
