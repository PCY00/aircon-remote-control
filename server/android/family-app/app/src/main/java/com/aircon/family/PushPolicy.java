package com.aircon.family;

import java.util.Map;
import java.util.Set;

/** Pure receive gate shared by foreground and background callbacks. */
final class PushPolicy {
    static boolean accepts(boolean enabled,String uid,String binding,Map<String,String> data,Set<String> seen) {
        String id=data.get("message_id"),kind=data.get("kind");
        return enabled && uid!=null && uid.equals(data.get("recipient")) && binding!=null && !binding.isEmpty()
            && binding.equals(data.get("binding")) && id!=null
            && id.matches("[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}")
            && ("event".equals(kind) || "test".equals(kind)) && !seen.contains(id);
    }
}
