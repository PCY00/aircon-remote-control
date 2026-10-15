package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class TemperatureDialTest {
    @Test public void sweepGrowsLinearlyFromAnEmptyArcAt17ToTheFullArcAt30() {
        assertEquals(0f,TemperatureDial.sweepFor(17),0.001f);
        assertEquals(270f,TemperatureDial.sweepFor(30),0.001f);
        assertEquals(7*270f/13,TemperatureDial.sweepFor(24),0.001f);
        assertEquals("Out-of-range drafts are drawn at the nearest end",0f,TemperatureDial.sweepFor(10),0.001f);
        assertEquals(270f,TemperatureDial.sweepFor(35),0.001f);
    }
    @Test public void arcEndsAndTopMapToTheExpectedTemperatures() {
        assertEquals(17,TemperatureDial.temperatureForAngle(135));
        assertEquals(30,TemperatureDial.temperatureForAngle(45));
        assertEquals(30,TemperatureDial.temperatureForAngle(405));
        assertEquals("Straight up is the middle of the range",24,TemperatureDial.temperatureForAngle(270));
        assertEquals("A few degrees past the start still rounds to 17",17,TemperatureDial.temperatureForAngle(140));
        assertEquals(18,TemperatureDial.temperatureForAngle(135+270f/13));
    }
    @Test public void everyTemperatureSurvivesARoundTripThroughItsAngle() {
        for(int t=17;t<=30;t++)
            assertEquals(t,TemperatureDial.temperatureForAngle(TemperatureDial.START+TemperatureDial.sweepFor(t)));
    }
    @Test public void anglesSnapToWholeDegrees() {
        float step=270f/13;
        assertEquals(20,TemperatureDial.temperatureForAngle(135+3*step+step*0.4f));
        assertEquals(21,TemperatureDial.temperatureForAngle(135+3*step+step*0.6f));
    }
    @Test public void theBottomOpeningSnapsToTheNearerEnd() {
        assertTrue(TemperatureDial.inGap(90));
        assertFalse(TemperatureDial.inGap(135));
        assertFalse(TemperatureDial.inGap(45));
        assertEquals("Just right of the bottom belongs to 30",30,TemperatureDial.temperatureForAngle(80));
        assertEquals("Just left of the bottom belongs to 17",17,TemperatureDial.temperatureForAngle(100));
    }
    @Test public void draggingThroughTheOpeningNeverJumpsAcrossTheRange() {
        assertEquals(30,TemperatureDial.temperatureForDrag(100,30));
        assertEquals(17,TemperatureDial.temperatureForDrag(80,17));
        assertEquals(26,TemperatureDial.temperatureForDrag(TemperatureDial.START+TemperatureDial.sweepFor(26),18));
    }
    @Test public void touchAnglesFollowCanvasDegrees() {
        assertEquals(0f,TemperatureDial.angleOf(1,0),0.001f);
        assertEquals(90f,TemperatureDial.angleOf(0,1),0.001f);
        assertEquals(180f,TemperatureDial.angleOf(-1,0),0.001f);
        assertEquals(270f,TemperatureDial.angleOf(0,-1),0.001f);
        assertEquals(17,TemperatureDial.temperatureForAngle(TemperatureDial.angleOf(-1,1)));
        assertEquals(30,TemperatureDial.temperatureForAngle(TemperatureDial.angleOf(1,1)));
    }
    @Test public void clampKeepsTheSupportedCoolingRange() {
        assertEquals(17,TemperatureDial.clamp(16));
        assertEquals(30,TemperatureDial.clamp(31));
        assertEquals(22,TemperatureDial.clamp(22));
    }
}
