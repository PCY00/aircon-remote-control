package com.aircon.family;

/** Display mapping for the cooling fan bars and the dial caption; the command values stay in {@link AirconUi}. */
final class FanLevels {
    private FanLevels() {}

    /** Short names under the dial; index matches {@link AirconUi#FANS}. */
    static final String[] SHORT = {"자동", "약", "중", "강"};
    /** Bars 1–3 stand for 약풍·중풍·강풍; index 0 (자동) is the separate pill. */
    static final int BARS = 3;

    /** A bar is filled up to the selected level; 자동 fills none. */
    static boolean filled(int bar, int fan) { return fan > 0 && bar >= 1 && bar <= fan; }

    /** Relative bar height in quarters of the tallest bar: 약 2/4, 중 3/4, 강 4/4. */
    static int heightQuarters(int bar) { return Math.max(1, Math.min(BARS, bar)) + 1; }

    static String dialCaption(int mode, int fan) {
        if (mode != 0) return "온도·바람은 냉방에서 선택해요";
        int index = fan >= 0 && fan < SHORT.length ? fan : 0;
        return AirconUi.MODES[0] + " · 바람 " + SHORT[index];
    }
}
