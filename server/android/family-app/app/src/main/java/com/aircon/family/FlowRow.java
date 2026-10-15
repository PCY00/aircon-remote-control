package com.aircon.family;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** Wraps chips onto the next line, so long labels and large font scales never clip. */
final class FlowRow extends ViewGroup {
    private final int gapX, gapY;

    FlowRow(Context context, int gapX, int gapY) { super(context); this.gapX = gapX; this.gapY = gapY; }

    @Override protected void onMeasure(int widthSpec, int heightSpec) {
        boolean bounded = MeasureSpec.getMode(widthSpec) != MeasureSpec.UNSPECIFIED;
        int available = MeasureSpec.getSize(widthSpec) - getPaddingLeft() - getPaddingRight();
        int x = 0, y = 0, line = 0, widest = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View child = getChildAt(i);
            if (child.getVisibility() == GONE) continue;
            child.measure(MeasureSpec.makeMeasureSpec(Math.max(0, available), bounded ? MeasureSpec.AT_MOST : MeasureSpec.UNSPECIFIED),
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED));
            int width = child.getMeasuredWidth(), height = child.getMeasuredHeight();
            if (x > 0 && bounded && x + width > available) { y += line + gapY; x = 0; line = 0; }
            x += width + gapX; line = Math.max(line, height); widest = Math.max(widest, x - gapX);
        }
        int width = (bounded ? available : widest) + getPaddingLeft() + getPaddingRight();
        int height = y + line + getPaddingTop() + getPaddingBottom();
        setMeasuredDimension(resolveSize(width, widthSpec), resolveSize(height, heightSpec));
    }

    @Override protected void onLayout(boolean changed, int left, int top, int right, int bottom) {
        int available = right - left - getPaddingLeft() - getPaddingRight();
        boolean rtl = getLayoutDirection() == LAYOUT_DIRECTION_RTL;
        int x = 0, y = 0, line = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View child = getChildAt(i);
            if (child.getVisibility() == GONE) continue;
            int width = child.getMeasuredWidth(), height = child.getMeasuredHeight();
            if (x > 0 && x + width > available) { y += line + gapY; x = 0; line = 0; }
            int start = rtl ? right - left - getPaddingRight() - x - width : getPaddingLeft() + x;
            child.layout(start, getPaddingTop() + y, start + width, getPaddingTop() + y + height);
            x += width + gapX; line = Math.max(line, height);
        }
    }
}
