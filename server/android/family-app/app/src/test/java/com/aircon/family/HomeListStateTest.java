package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class HomeListStateTest {
    @Test public void failedFirstConnectionIsUnavailableRatherThanAnEmptyHomeList() {
        HomeListState<String> state=new HomeListState<>("");
        state.begin();
        assertEquals(HomeListState.Status.LOADING,state.status());
        state.fail("connection failed");
        assertEquals(HomeListState.Status.UNAVAILABLE,state.status());
        assertFalse(state.refreshing());
    }
    @Test public void emptyRequiresAnActualSuccessfulServerReply() {
        HomeListState<String> state=new HomeListState<>("");
        state.begin(); state.succeed("[]",0);
        assertEquals(HomeListState.Status.EMPTY,state.status());
    }
    @Test public void serverRestartFailureKeepsLastConfirmedHomesUntilRetrySucceeds() {
        HomeListState<String> state=new HomeListState<>("");
        state.succeed("my existing home",1);
        state.begin(); state.fail("old temporary address");
        assertEquals(HomeListState.Status.STALE,state.status());
        assertEquals("my existing home",state.snapshot());
        assertEquals(1,state.count());
        state.begin(); state.succeed("my existing home",1);
        assertEquals(HomeListState.Status.READY,state.status());
        assertNull(state.error());
    }
    @Test public void abandonedRefreshStaysRefreshingSoReturningToTheListReloadsIt() {
        HomeListState<String> state=new HomeListState<>("");
        state.succeed("my existing home",1); state.begin();
        assertTrue(state.refreshing());
        assertEquals(HomeListState.Status.READY,state.status());
        state.begin(); state.succeed("my existing home",1);
        assertFalse(state.refreshing());
    }
    @Test public void accountOrServerChangeClearsThePreviousHouseholdSnapshot() {
        HomeListState<String> state=new HomeListState<>("");
        state.succeed("previous account home",1);
        state.reset(); state.begin(); state.fail("connection failed");
        assertEquals(HomeListState.Status.UNAVAILABLE,state.status());
        assertEquals("",state.snapshot());
        assertEquals(0,state.count());
    }
}
