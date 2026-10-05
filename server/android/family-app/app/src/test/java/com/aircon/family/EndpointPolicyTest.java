package com.aircon.family;
import org.junit.Test;
import static org.junit.Assert.*;
public class EndpointPolicyTest {
    @Test public void httpsOriginAndDebugLoopback() {
        assertEquals("https://house.example",EndpointPolicy.validate("https://house.example/",false));
        assertEquals("http://127.0.0.1:8001",EndpointPolicy.validate("http://127.0.0.1:8001",true));
    }
    @Test public void insecureOrAmbiguousOriginsRejected() {
        for(String value:new String[]{"http://house.example","https://user:pass@house.example","https://house.example/path","https://house.example?token=x","https://house.example#fragment","file:///tmp/key","https://house.example:99999"}) {
            try { EndpointPolicy.validate(value,true); fail(value); } catch(IllegalArgumentException expected) {}
        }
        try { EndpointPolicy.validate("http://127.0.0.1:8001",false); fail(); } catch(IllegalArgumentException expected) {}
    }
}
