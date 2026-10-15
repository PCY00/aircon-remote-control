package com.aircon.family;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Thin org.json → plain Java adapter. Everything after this point (Device, Inventory, Attention, Timeline)
 * works on maps and lists, because org.json is only a stub in JVM unit tests.
 */
final class JsonValues {
    private JsonValues() {}

    static Map<String,Object> map(JSONObject object) {
        Map<String,Object> result=new LinkedHashMap<>();
        if(object==null) return result;
        Iterator<String> keys=object.keys();
        while(keys.hasNext()) { String key=keys.next(); result.put(key,value(object.opt(key))); }
        return result;
    }
    static List<Object> list(JSONArray array) {
        List<Object> result=new ArrayList<>();
        if(array==null) return result;
        for(int i=0;i<array.length();i++) result.add(value(array.opt(i)));
        return result;
    }
    static Object value(Object value) {
        if(value==null || value==JSONObject.NULL) return null;
        if(value instanceof JSONObject) return map((JSONObject)value);
        if(value instanceof JSONArray) return list((JSONArray)value);
        return value;
    }
}
