package com.aircon.family;

/** One result check per aircon command; a superseded or abandoned check never updates the screen. */
final class CommandPoll {
    static final int MAX_ATTEMPTS=30;
    private String id;
    private int epoch;

    /** Returns false when this command already has a live check in the same screen generation. */
    boolean start(String command,int generation) {
        if(command==null || command.isEmpty() || (command.equals(id) && epoch==generation)) return false;
        id=command; epoch=generation; return true;
    }
    boolean active(String command,int generation) { return command!=null && command.equals(id) && epoch==generation; }
    void finish(String command) { if(command!=null && command.equals(id)) id=null; }
    /** Drops the live check and reports whether one was running, so it can resume from the server later. */
    boolean cancel() { boolean running=id!=null; id=null; return running; }
    /** Sign-in, permission and missing-command failures do not recover by asking again. */
    static boolean retryable(int status) { return status!=401 && status!=403 && status!=404; }
    /** A reply for an older command must not replace a newer latest_command. */
    static boolean current(String latest,String reply) { return latest==null || latest.isEmpty() || latest.equals(reply); }
}
