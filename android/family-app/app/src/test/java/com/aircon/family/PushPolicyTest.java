package com.aircon.family;
import java.util.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class PushPolicyTest {
    private Map<String,String> data() {
        Map<String,String> d=new HashMap<>();d.put("message_id","12345678-1234-1234-1234-123456789abc");
        d.put("recipient","owner");d.put("binding","current");d.put("kind","event");return d;
    }
    @Test public void rejectsLateDeliveryAfterLogoutAccountChangeAndTokenRotation() {
        Map<String,String> d=data();Set<String> none=Collections.emptySet();
        assertTrue(PushPolicy.accepts(true,"owner","current",d,none));
        assertFalse(PushPolicy.accepts(false,"owner","current",d,none));
        assertFalse(PushPolicy.accepts(true,null,"current",d,none));
        assertFalse(PushPolicy.accepts(true,"other-account","current",d,none));
        assertFalse(PushPolicy.accepts(true,"owner","new-binding",d,none));
        assertFalse(PushPolicy.accepts(true,"owner","",d,none));
    }
    @Test public void retriesCannotRedisplaySameMessageAndUnknownMessagesAreIgnored() {
        Map<String,String> d=data();
        assertFalse(PushPolicy.accepts(true,"owner","current",d,Set.of(d.get("message_id"))));
        d.put("kind","unexpected");assertFalse(PushPolicy.accepts(true,"owner","current",d,Collections.emptySet()));
        d=data();d.put("message_id","arbitrary-notification");assertFalse(PushPolicy.accepts(true,"owner","current",d,Collections.emptySet()));
        d=data();d.remove("recipient");assertFalse(PushPolicy.accepts(true,"owner","current",d,Collections.emptySet()));
    }
}
