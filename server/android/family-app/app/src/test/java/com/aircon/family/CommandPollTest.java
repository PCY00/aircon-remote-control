package com.aircon.family;

import org.junit.Test;
import static org.junit.Assert.*;

public class CommandPollTest {
    @Test public void reopeningTheControlScreenDoesNotStartASecondCheckForTheSameCommand() {
        CommandPoll poll=new CommandPoll();
        assertTrue(poll.start("x",3));
        assertFalse(poll.start("x",3));
        assertTrue(poll.active("x",3));
    }
    @Test public void aNewerCommandOrScreenGenerationSupersedesTheOldCheck() {
        CommandPoll poll=new CommandPoll();
        poll.start("x",3);
        assertTrue(poll.start("y",3));
        assertFalse(poll.active("x",3));
        assertTrue(poll.start("y",4));
        assertFalse(poll.active("y",3));
        assertTrue(poll.active("y",4));
    }
    @Test public void finishingAnOldCommandKeepsTheNewerCheck() {
        CommandPoll poll=new CommandPoll();
        poll.start("x",1); poll.start("y",1);
        poll.finish("x");
        assertTrue(poll.active("y",1));
        poll.finish("y");
        assertFalse(poll.active("y",1));
        assertTrue(poll.start("y",1));
    }
    @Test public void backgroundCancelReportsWhetherACheckMustResume() {
        CommandPoll poll=new CommandPoll();
        assertFalse(poll.cancel());
        poll.start("x",1);
        assertTrue(poll.cancel());
        assertFalse(poll.active("x",1));
        assertFalse(poll.cancel());
        assertFalse(poll.start("",1));
        assertFalse(poll.start(null,1));
    }
    @Test public void revokedSignedOutOrMissingCommandsStopInsteadOfRetrying() {
        assertFalse(CommandPoll.retryable(401));
        assertFalse(CommandPoll.retryable(403));
        assertFalse(CommandPoll.retryable(404));
        assertTrue(CommandPoll.retryable(0));
        assertTrue(CommandPoll.retryable(500));
        assertTrue(CommandPoll.retryable(503));
    }
    @Test public void anOlderReplyCannotReplaceANewerLatestCommand() {
        assertTrue(CommandPoll.current("x","x"));
        assertTrue(CommandPoll.current(null,"x"));
        assertTrue(CommandPoll.current("","x"));
        assertFalse(CommandPoll.current("y","x"));
    }
}
