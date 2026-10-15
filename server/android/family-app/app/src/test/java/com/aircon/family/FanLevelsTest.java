package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class FanLevelsTest {
    @Test public void barsFillUpToTheSelectedLevelAndAutoFillsNone() {
        for(int bar=1;bar<=FanLevels.BARS;bar++) assertFalse("자동",FanLevels.filled(bar,0));
        assertTrue(FanLevels.filled(1,1));assertFalse(FanLevels.filled(2,1));
        assertTrue(FanLevels.filled(1,2));assertTrue(FanLevels.filled(2,2));assertFalse(FanLevels.filled(3,2));
        for(int bar=1;bar<=FanLevels.BARS;bar++) assertTrue("강풍",FanLevels.filled(bar,3));
        assertEquals("Bars match the 약/중/강 fan values",AirconUi.FANS.length-1,FanLevels.BARS);
    }
    @Test public void barsGrowTaller() {
        assertTrue(FanLevels.heightQuarters(1)<FanLevels.heightQuarters(2));
        assertTrue(FanLevels.heightQuarters(2)<FanLevels.heightQuarters(3));
        assertEquals(4,FanLevels.heightQuarters(3));
    }
    @Test public void dialCaptionShowsModeAndFanOnlyWhileCooling() {
        assertEquals("냉방 · 바람 자동",FanLevels.dialCaption(0,0));
        assertEquals("냉방 · 바람 강",FanLevels.dialCaption(0,3));
        assertEquals("온도·바람은 냉방에서 선택해요",FanLevels.dialCaption(2,3));
        assertEquals(AirconUi.FANS.length,FanLevels.SHORT.length);
    }
}
