package com.aircon.family;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Builds the plain maps/lists JsonValues produces from a server reply (null values allowed). */
final class TestMaps {
    private TestMaps() {}
    static Map<String,Object> map(Object... pairs) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(int i=0;i<pairs.length;i+=2) result.put((String)pairs[i],pairs[i+1]);
        return result;
    }
    static List<Object> list(Object... values) { return new ArrayList<>(Arrays.asList(values)); }
    static final String DOOR="0123456789abcdef0123456789abcdef", CLIMATE="fedcba9876543210fedcba9876543210",
        AIRCON="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    static Map<String,Object> device(String id,String name,String room,String type,List<Object> capabilities,Map<String,Object> state,Object reportedAt) {
        return map("id",id,"name",name,"room",room,"type",type,"capabilities",capabilities,"state",state,"reported_at",reportedAt,"controllable",type.equals("air_conditioner"));
    }
    static Device door(String contact,Double battery,Double reportedAt) {
        Map<String,Object> state=map("contact",contact);if(battery!=null) state.put("battery_percent",battery);
        return Device.from(device(DOOR,"현관문","현관","door_sensor",list("contact","battery"),state,reportedAt));
    }
    static Device climate(Double temperature,Double humidity,Double reportedAt) {
        return Device.from(device(CLIMATE,"거실 온습도","거실","climate_sensor",list("temperature","humidity","battery"),
            map("temperature_c",temperature,"humidity_percent",humidity,"battery_percent",80.0),reportedAt));
    }
    static Device aircon(Map<String,Object> state) {
        return Device.from(device(AIRCON,"거실 에어컨","거실","air_conditioner",list("power","setpoint","mode","fan","actions"),state,null));
    }
    static AppEvent event(long id,String kind,double receivedAt,Map<String,Object> payload) {
        return AppEvent.from(map("id",id,"kind",kind,"received_at",receivedAt,"payload",payload));
    }
    static Inventory inventory(Double updatedAt,Boolean online,Device... devices) {
        return new Inventory(Arrays.asList(devices),updatedAt,online,false,true);
    }
}
