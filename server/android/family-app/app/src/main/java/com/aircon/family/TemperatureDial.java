package com.aircon.family;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

/**
 * 270° cooling temperature dial. It only edits the unsent draft through its listener; sending stays
 * behind the activity's confirmation dialog. Outside cooling the arc is greyed and ignores touches.
 */
final class TemperatureDial extends View {
    static final int MIN = 17, MAX = 30;
    /** Android canvas degrees: 0° is 3 o'clock and angles grow clockwise, so the opening sits at the bottom. */
    static final float START = 135f, SWEEP = 270f;

    interface Listener { void changed(int temperature); }

    private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG), progress = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint thumb = new Paint(Paint.ANTI_ALIAS_FLAG), thumbRing = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint value = new Paint(Paint.ANTI_ALIAS_FLAG), caption = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ends = new Paint(Paint.ANTI_ALIAS_FLAG), ring = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private final int secondary;
    private int temperature = 24;
    private boolean adjustable = true, dragging;
    private String mode = "", note = "";
    private Listener listener;

    TemperatureDial(Context context, int trackColor, int accentColor, int primaryColor, int secondaryColor) {
        super(context);
        secondary = secondaryColor;
        track.setStyle(Paint.Style.STROKE); track.setStrokeCap(Paint.Cap.ROUND); track.setColor(trackColor); track.setStrokeWidth(px(14));
        progress.setStyle(Paint.Style.STROKE); progress.setStrokeCap(Paint.Cap.ROUND); progress.setColor(accentColor); progress.setStrokeWidth(px(14));
        thumb.setColor(primaryColor);
        thumbRing.setStyle(Paint.Style.STROKE); thumbRing.setColor(accentColor); thumbRing.setStrokeWidth(px(3));
        value.setColor(primaryColor); value.setTypeface(Typeface.DEFAULT_BOLD); value.setTextAlign(Paint.Align.CENTER);
        caption.setColor(secondaryColor); caption.setTextAlign(Paint.Align.CENTER);
        ends.setColor(secondaryColor); ends.setTextAlign(Paint.Align.CENTER); ends.setTextSize(sp(12));
        ring.setStyle(Paint.Style.STROKE); ring.setStrokeWidth(px(2)); ring.setColor(accentColor); ring.setAlpha(140);
        setFocusable(true); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        describe();
    }

    // ---- Pure math (unit-tested without a device) ----

    static int clamp(int temperature) { return Math.max(MIN, Math.min(MAX, temperature)); }

    /** Progress sweep in degrees for a temperature; 17° is an empty arc and 30° the full 270°. */
    static float sweepFor(int temperature) { return (clamp(temperature) - MIN) * SWEEP / (MAX - MIN); }

    static float normalize(float degrees) { float d = degrees % 360f; return d < 0 ? d + 360f : d; }

    /** Touch angle around the centre in canvas degrees (0° = right, 90° = down). */
    static float angleOf(float dx, float dy) { return normalize((float) Math.toDegrees(Math.atan2(dy, dx))); }

    static boolean inGap(float degrees) { return normalize(degrees - START) > SWEEP; }

    /** Snaps an angle to the nearest whole degree Celsius; inside the bottom opening the nearer end wins. */
    static int temperatureForAngle(float degrees) {
        float along = normalize(degrees - START);
        if (along > SWEEP) return along - SWEEP < (360f - SWEEP) / 2f ? MAX : MIN;
        return clamp(MIN + Math.round(along / SWEEP * (MAX - MIN)));
    }

    /** While dragging, a finger sliding through the opening keeps the end it came from instead of jumping 17↔30. */
    static int temperatureForDrag(float degrees, int current) {
        if (inGap(degrees)) return current * 2 >= MIN + MAX ? MAX : MIN;
        return temperatureForAngle(degrees);
    }

    // ---- State ----

    void setListener(Listener listener) { this.listener = listener; }

    int temperature() { return temperature; }

    /** Shows the draft without notifying the listener. Outside cooling the centre shows the mode name instead. */
    void bind(boolean adjustable, int temperature, String mode, String note) {
        this.adjustable = adjustable; this.temperature = clamp(temperature);
        this.mode = mode == null ? "" : mode; this.note = note == null ? "" : note;
        if (!adjustable) dragging = false;
        describe(); invalidate();
    }

    private void change(int next) {
        next = clamp(next);
        if (next == temperature) return;
        temperature = next; describe(); invalidate();
        sendAccessibilityEvent(AccessibilityEvent.TYPE_VIEW_SELECTED);
        if (listener != null) listener.changed(temperature);
    }

    private boolean step(int delta) {
        if (!adjustable) return false;
        int before = temperature; change(temperature + delta); return before != temperature;
    }

    private void describe() {
        setContentDescription(adjustable ? "희망 온도 " + temperature + "도" : mode + " 모드. " + note);
    }

    // ---- Layout and drawing ----

    private float px(float dp) { return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, dp, getResources().getDisplayMetrics()); }
    private float sp(float sp) { return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, sp, getResources().getDisplayMetrics()); }

    @Override protected void onMeasure(int widthSpec, int heightSpec) {
        int wanted = (int) px(264);
        int width = resolveSize(wanted, widthSpec), height = resolveSize(wanted, heightSpec);
        int side = Math.min(width, height);
        setMeasuredDimension(side, side);
    }

    private float thumbRadius() { return px(13); }

    private float radius() { return Math.min(getWidth(), getHeight()) / 2f - thumbRadius() - px(4); }

    /** Shrinks a single line so it stays inside the ring, also at large font scales. */
    private void fit(Paint paint, float size, String text, float width) {
        paint.setTextSize(size);
        float measured = paint.measureText(text);
        if (measured > width && measured > 0) paint.setTextSize(size * width / measured);
    }

    @Override protected void onDraw(Canvas canvas) {
        float cx = getWidth() / 2f, cy = getHeight() / 2f, r = radius();
        oval.set(cx - r, cy - r, cx + r, cy + r);
        canvas.drawArc(oval, START, SWEEP, false, track);
        float inner = (r - px(14)) * 2f * 0.86f;
        if (adjustable) {
            float sweep = sweepFor(temperature);
            if (sweep > 0) canvas.drawArc(oval, START, sweep, false, progress);
            double angle = Math.toRadians(START + sweep);
            float tx = cx + (float) (r * Math.cos(angle)), ty = cy + (float) (r * Math.sin(angle));
            canvas.drawCircle(tx, ty, thumbRadius(), thumb);
            canvas.drawCircle(tx, ty, thumbRadius() - px(1.5f), thumbRing);
            String big = temperature + "°";
            fit(value, sp(48), big, inner);
            canvas.drawText(big, cx, cy + value.getTextSize() * 0.2f, value);
        } else {
            fit(value, sp(34), mode, inner);
            canvas.drawText(mode, cx, cy + value.getTextSize() * 0.2f, value);
        }
        fit(caption, sp(14), note, inner);
        canvas.drawText(note, cx, cy + value.getTextSize() * 0.2f + caption.getTextSize() * 1.9f, caption);
        // Range ends beside the opening of the arc.
        ends.setColor(secondary); ends.setAlpha(adjustable ? 255 : 90);
        double left = Math.toRadians(START), right = Math.toRadians(START + SWEEP);
        float below = px(26);
        canvas.drawText(MIN + "°", cx + (float) (r * Math.cos(left)), cy + (float) (r * Math.sin(left)) + below, ends);
        canvas.drawText(MAX + "°", cx + (float) (r * Math.cos(right)), cy + (float) (r * Math.sin(right)) + below, ends);
        if (isFocused()) {
            // Keyboard / switch-access focus ring inside the dial.
            canvas.drawCircle(cx, cy, r - px(22), ring);
        }
    }

    @Override protected void onFocusChanged(boolean gained, int direction, android.graphics.Rect previous) {
        super.onFocusChanged(gained, direction, previous); invalidate();
    }

    // ---- Touch ----

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (!adjustable || !isEnabled()) return false;
        float dx = event.getX() - getWidth() / 2f, dy = event.getY() - getHeight() / 2f;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN: {
                double distance = Math.hypot(dx, dy), r = radius();
                float angle = angleOf(dx, dy);
                // Only the ring itself starts a drag: the centre and the opening stay free for scrolling.
                if (distance < r - px(44) || distance > r + px(30) || inGap(angle)) return false;
                dragging = true; setPressed(true);
                if (getParent() != null) getParent().requestDisallowInterceptTouchEvent(true);
                change(temperatureForAngle(angle));
                return true;
            }
            case MotionEvent.ACTION_MOVE:
                if (!dragging) return false;
                change(temperatureForDrag(angleOf(dx, dy), temperature));
                return true;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                if (!dragging) return false;
                dragging = false; setPressed(false);
                if (getParent() != null) getParent().requestDisallowInterceptTouchEvent(false);
                return true;
            default:
                return dragging;
        }
    }

    // ---- Keyboard and accessibility ----

    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (adjustable && keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { step(-1); return true; }
        if (adjustable && keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { step(1); return true; }
        return super.onKeyDown(keyCode, event);
    }

    @Override public CharSequence getAccessibilityClassName() {
        return adjustable ? "android.widget.SeekBar" : View.class.getName();
    }

    @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
        super.onInitializeAccessibilityNodeInfo(info);
        if (!adjustable) return;
        info.setRangeInfo(AccessibilityNodeInfo.RangeInfo.obtain(AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_INT, MIN, MAX, temperature));
        if (temperature < MAX) info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD);
        if (temperature > MIN) info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD);
        info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS);
    }

    @Override public boolean performAccessibilityAction(int action, Bundle arguments) {
        if (adjustable) {
            if (action == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) return step(1);
            if (action == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) return step(-1);
            if (action == android.R.id.accessibilityActionSetProgress && arguments != null
                    && arguments.containsKey(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE)) {
                change(Math.round(arguments.getFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE)));
                return true;
            }
        }
        return super.performAccessibilityAction(action, arguments);
    }
}
