package com.aircon.family;

/** An unavailable server must never be presented as a confirmed empty household list. */
final class HomeListState<T> {
    enum Status { LOADING, UNAVAILABLE, EMPTY, READY, STALE }
    private final T empty;
    private T snapshot;
    private int count;
    private boolean loaded, refreshing;
    private String error;

    HomeListState(T empty) { this.empty=empty; reset(); }
    void reset() { snapshot=empty; count=0; loaded=false; refreshing=false; error=null; }
    void begin() { refreshing=true; error=null; }
    void succeed(T value,int size) {
        if(value==null || size<0) throw new IllegalArgumentException("Invalid home list");
        snapshot=value; count=size; loaded=true; refreshing=false; error=null;
    }
    void fail(String message) { refreshing=false; error=message; }
    T snapshot() { return snapshot; }
    int count() { return count; }
    boolean refreshing() { return refreshing; }
    String error() { return error; }
    Status status() {
        if(error!=null) return loaded ? Status.STALE : Status.UNAVAILABLE;
        if(!loaded) return Status.LOADING;
        return count==0 ? Status.EMPTY : Status.READY;
    }
}
