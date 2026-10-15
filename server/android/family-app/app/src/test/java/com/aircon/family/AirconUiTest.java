package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class AirconUiTest {
    @Test public void viewerOfflineAndPendingCommandsCannotSend() {
        assertFalse(AirconUi.canSend(false,true,"sent"));
        assertFalse(AirconUi.canSend(true,false,"sent"));
        assertFalse(AirconUi.canSend(true,true,"queued"));
        assertFalse(AirconUi.canSend(true,true,"dispatched"));
        assertTrue(AirconUi.canSend(true,true,"sent"));
    }
    @Test public void sentMeansInfraredTransmissionAndUnknownRequiresCheckingTheAppliance() {
        assertTrue(AirconUi.description("sent").contains("실제 작동은 에어컨에서 확인"));
        assertTrue(AirconUi.description("unknown").contains("다시 누르기 전에"));
        assertFalse(AirconUi.description("unknown").contains("실행하지 않았"));
    }
    @Test public void changingModePreservesTheUnsentCoolingDraft() {
        AirconUi.Draft draft=new AirconUi.Draft();draft.temperature=19;draft.fan=3;
        draft.mode=2;assertEquals("mode_dry",draft.action());
        draft.mode=0;assertEquals("cool_19_high",draft.action());
        assertEquals("냉방 19°C · 강풍",AirconUi.actionLabel(draft.action()));
    }
    @Test public void unsupportedCoolingValuesCannotBecomeCommands() {
        for(int[] values:new int[][]{{16,0},{31,0},{24,-1},{24,4}}) {
            try { AirconUi.coolingAction(values[0],values[1]);fail("Invalid setting accepted"); }
            catch(IllegalArgumentException expected){}
        }
        assertEquals("cool_17_auto",AirconUi.coolingAction(17,0));
        assertEquals("cool_30_high",AirconUi.coolingAction(30,3));
    }
    @Test public void toggleCommandsExplainThatTheyChangeTheCurrentApplianceState() {
        assertTrue(AirconUi.confirmation("swing_toggle").contains("누를 때마다"));
        assertTrue(AirconUi.confirmation("led_toggle").contains("현재 상태를 읽지 못해요"));
        assertEquals("풍향 고정",AirconUi.actionLabel("airflow_fix"));
        assertEquals("제습 운전",AirconUi.actionLabel("mode_dry"));
    }
    @Test public void economyExplainsItKeepsTheCoolingTemperatureAndOnlyWorksWhileCooling() {
        String text=AirconUi.confirmation("economy");
        assertTrue(text.startsWith("절전 신호를 보내요."));
        assertTrue(text.contains("냉방 온도는 그대로"));
        assertTrue(text.contains("바람만 자동"));
        assertTrue(text.contains("냉방 중에만"));
        assertTrue(text.contains("실패로 표시"));
        assertFalse(AirconUi.confirmation("turbo").contains("냉방 중에만"));
        assertTrue(AirconUi.description("failed","economy").contains("냉방 중에만"));
        assertEquals(AirconUi.description("failed"),AirconUi.description("failed","turbo"));
        assertEquals(AirconUi.description("sent"),AirconUi.description("sent","economy"));
    }
    @Test public void oneLineStatusUsesShortActionsAndStateWords() {
        assertEquals("냉방 24°",AirconUi.shortLabel("cool_24_high"));
        assertEquals("냉방 24°",AirconUi.shortLabel("cool_on"));
        assertEquals("끄기",AirconUi.shortLabel("power_off"));
        assertEquals("제습",AirconUi.shortLabel("mode_dry"));
        assertEquals("절전",AirconUi.shortLabel("economy"));
        assertEquals("전달 중",AirconUi.stateLabel("queued"));assertEquals("전달 중",AirconUi.stateLabel("dispatched"));
        assertEquals("전달됨",AirconUi.stateLabel("sent"));assertEquals("결과 모름",AirconUi.stateLabel("unknown"));
        assertEquals("",AirconUi.stateLabel(""));
        assertTrue(AirconUi.problem("failed"));assertTrue(AirconUi.problem("unknown"));assertTrue(AirconUi.problem("expired"));
        assertFalse(AirconUi.problem("sent"));assertFalse(AirconUi.problem("queued"));
    }
    @Test public void unsentDraftSurvivesRecreationAndRejectsTamperedValues() {
        AirconUi.Draft draft=new AirconUi.Draft();draft.temperature=19;draft.mode=0;draft.fan=3;
        int[] saved=new int[6];System.arraycopy(draft.save(),0,saved,3,3);
        AirconUi.Draft restored=AirconUi.Draft.restore(saved,3);
        assertEquals("cool_19_high",restored.action());
        AirconUi.Draft invalid=AirconUi.Draft.restore(new int[]{40,9,-1},0);
        assertEquals(24,invalid.temperature);assertEquals(0,invalid.mode);assertEquals(0,invalid.fan);
        assertEquals("cool_24_auto",AirconUi.Draft.restore(null,0).action());
        assertEquals("cool_24_auto",AirconUi.Draft.restore(new int[]{19,0},0).action());
    }
}
