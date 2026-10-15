package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class ApiClientTest {
    @Test public void nestingDepthIgnoresBracketsInsideStringsAndCountsTheDeepestLevel() {
        StringBuilder deep=new StringBuilder("{\"a\":");
        for(int i=0;i<64;i++) deep.append('[');
        for(int i=0;i<64;i++) deep.append(']');
        deep.append('}');
        assertEquals(65,ApiClient.depth(deep.toString()));
        assertTrue(ApiClient.depth(deep.toString())>ApiClient.MAX_DEPTH);
        assertEquals(3,ApiClient.depth("{\"a\":[\"]]]]]\",{\"b\":\"\\\"{\"}],\"c\":1}"));
        assertEquals(0,ApiClient.depth("\"[[[[\""));
        assertEquals(3,ApiClient.depth("{\"homes\":[{},{}],\"user_id\":\"u\"}"));
    }
}
