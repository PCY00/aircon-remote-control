package com.aircon.family;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Typed reads from the plain maps and lists {@link JsonValues} makes out of a server reply.
 * Kept free of org.json so the parsing rules run in JVM tests.
 */
final class Plain {
    private Plain() {}

    @SuppressWarnings("unchecked")
    static Map<String,Object> map(Object value) {
        return value instanceof Map ? (Map<String,Object>)value : Collections.emptyMap();
    }
    @SuppressWarnings("unchecked")
    static List<Object> list(Object value) {
        return value instanceof List ? (List<Object>)value : Collections.emptyList();
    }
    /** A string, or null for anything else. */
    static String text(Object value) { return value instanceof String ? (String)value : null; }
    static String text(Object value,String fallback) { String text=text(value); return text==null ? fallback : text; }
    /** A finite number (booleans are not numbers), or null. */
    static Double number(Object value) {
        if(!(value instanceof Number)) return null;
        double number=((Number)value).doubleValue();
        return Double.isFinite(number) ? number : null;
    }
    static boolean flag(Object value) { return Boolean.TRUE.equals(value); }
    /** Drops control and format characters (Unicode Cc/Cf) and trims; the server already does this, the app does not rely on it. */
    static String clean(String value,int maximum) {
        if(value==null) return "";
        StringBuilder result=new StringBuilder();
        for(int i=0;i<value.length();i++) {
            char c=value.charAt(i);int type=Character.getType(c);
            if(type!=Character.CONTROL && type!=Character.FORMAT) result.append(c);
        }
        String text=result.toString().trim();
        return text.length()>maximum ? text.substring(0,maximum) : text;
    }
}
