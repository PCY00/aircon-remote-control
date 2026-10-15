package com.aircon.family;

import java.util.ArrayList;
import java.util.List;

/** Device type → the "종류별 모아보기" category, its label and icons. Unknown types fall into 기타. */
final class DeviceCategory {
    private DeviceCategory() {}

    static final String HVAC="hvac", LIGHT="light", SECURITY="security", ENVIRONMENT="environment",
        SAFETY="safety", POWER="power", OTHER="other";
    /** Chip order on the home tab. */
    static final String[] KEYS={HVAC,LIGHT,SECURITY,ENVIRONMENT,SAFETY,POWER,OTHER};

    static String of(String type) {
        switch(type==null ? "" : type) {
            case "air_conditioner": return HVAC;
            case "light": return LIGHT;
            case "door_sensor": case "motion_sensor": return SECURITY;
            case "climate_sensor": return ENVIRONMENT;
            case "leak_sensor": case "smoke_sensor": return SAFETY;
            case "plug": return POWER;
            default: return OTHER;
        }
    }
    static String label(String category) {
        switch(category) {
            case HVAC: return "냉난방";
            case LIGHT: return "조명";
            case SECURITY: return "보안";
            case ENVIRONMENT: return "환경";
            case SAFETY: return "안전";
            case POWER: return "전력";
            default: return "기타";
        }
    }
    static String icon(String category) {
        switch(category) {
            case HVAC: return "aircon";
            case LIGHT: return "bulb";
            case SECURITY: return "door";
            case ENVIRONMENT: return "thermometer";
            case SAFETY: return "droplet";
            case POWER: return "plug";
            default: return "hub";
        }
    }
    static String typeIcon(String type) {
        switch(type==null ? "" : type) {
            case "air_conditioner": return "aircon";
            case "light": return "bulb";
            case "door_sensor": return "door";
            case "motion_sensor": return "motion";
            case "climate_sensor": return "thermometer";
            case "leak_sensor": return "droplet";
            case "smoke_sensor": return "warning";
            case "plug": return "plug";
            default: return "hub";
        }
    }
    /** Name used when a device arrives without one (older server fallback, or an empty name). */
    static String typeLabel(String type) {
        switch(type==null ? "" : type) {
            case "air_conditioner": return "에어컨";
            case "light": return "전등";
            case "door_sensor": return "문";
            case "motion_sensor": return "움직임 센서";
            case "climate_sensor": return "온습도";
            case "leak_sensor": return "누수 센서";
            case "smoke_sensor": return "연기 센서";
            case "plug": return "플러그";
            default: return "기기";
        }
    }
    /** Categories that have at least one device, in chip order. */
    static List<String> present(List<Device> devices) {
        List<String> result=new ArrayList<>();
        for(String key:KEYS) for(Device device:devices) if(device.category().equals(key)) { result.add(key); break; }
        return result;
    }
    static List<Device> members(List<Device> devices,String category) {
        List<Device> result=new ArrayList<>();
        for(Device device:devices) if(device.category().equals(category)) result.add(device);
        return result;
    }
}
