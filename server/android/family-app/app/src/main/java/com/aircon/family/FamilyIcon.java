package com.aircon.family;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;

/** Small native line icons, independent of fonts, emoji and remote image assets. */
final class FamilyIcon extends Drawable {
    private final String name;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final int size;

    FamilyIcon(String name, int color, int size) {
        this.name = name; this.size = size;
        paint.setColor(color); paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(1.7f); paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeJoin(Paint.Join.ROUND);
        setBounds(0, 0, size, size);
    }
    private void path(Canvas c, float... points) {
        Path p = new Path(); p.moveTo(points[0], points[1]);
        for (int i = 2; i < points.length; i += 2) p.lineTo(points[i], points[i + 1]);
        c.drawPath(p, paint);
    }
    @Override public void draw(Canvas canvas) {
        int saved = canvas.save();
        canvas.translate(getBounds().left, getBounds().top);
        canvas.scale(getBounds().width() / 24f, getBounds().height() / 24f);
        switch (name) {
            case "home":
                path(canvas,3,10,12,3,21,10); path(canvas,5,9,5,21,10,21,10,14,14,14,14,21,19,21,19,9); break;
            case "history":
                canvas.drawCircle(12,12,8,paint); path(canvas,12,7,12,12,16,14); break;
            case "settings":
                path(canvas,4,6,20,6); path(canvas,4,12,20,12); path(canvas,4,18,20,18);
                canvas.drawCircle(9,6,2,paint); canvas.drawCircle(16,12,2,paint); canvas.drawCircle(8,18,2,paint); break;
            case "bell":
                canvas.drawArc(6,4,18,16,180,180,false,paint);
                path(canvas,6,10,6,15,4,18,20,18,18,15,18,10); canvas.drawArc(10,18,14,22,0,180,false,paint); break;
            case "door":
                path(canvas,5,21,5,3,17,3,17,21,5,21); canvas.drawCircle(13,12,.7f,paint); path(canvas,17,21,21,21); break;
            case "climate":
                canvas.drawRoundRect(8,3,14,16,3,3,paint); canvas.drawCircle(11,18,4,paint); path(canvas,11,8,11,18); path(canvas,18,5,21,5,18,10,21,10); break;
            case "family":
                canvas.drawCircle(9,7,3,paint); canvas.drawCircle(18,9,2,paint);
                canvas.drawArc(3,13,15,25,180,180,false,paint); canvas.drawArc(15,14,22,23,180,170,false,paint); break;
            case "hub":
                canvas.drawRoundRect(4,6,20,20,3,3,paint); path(canvas,8,3,8,6); path(canvas,16,3,16,6);
                canvas.drawCircle(9,13,1,paint); path(canvas,13,13,16,13); break;
            case "warning": path(canvas,12,3,22,21,2,21,12,3); path(canvas,12,9,12,14); canvas.drawCircle(12,18,.5f,paint); break;
            case "back": path(canvas,14,5,7,12,14,19); path(canvas,7,12,21,12); break;
            case "chevron": path(canvas,9,6,15,12,9,18); break;
            case "refresh": canvas.drawArc(4,4,20,20,40,300,false,paint); path(canvas,20,4,20,10,14,10); break;
            case "add": path(canvas,12,5,12,19); path(canvas,5,12,19,12); break;
            case "logout": path(canvas,10,4,4,4,4,20,10,20); path(canvas,9,12,21,12,17,8); path(canvas,21,12,17,16); break;
            case "network": canvas.drawArc(2,3,22,23,220,100,false,paint); canvas.drawArc(6,8,18,20,220,100,false,paint); canvas.drawCircle(12,18,1,paint); break;
            case "trash": path(canvas,4,6,20,6); path(canvas,9,3,15,3,15,6); path(canvas,6,6,7,21,17,21,18,6); path(canvas,10,10,10,17); path(canvas,14,10,14,17); break;
            default: canvas.drawCircle(12,12,8,paint);
        }
        canvas.restoreToCount(saved);
    }
    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); }
    @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    @Override public int getIntrinsicWidth() { return size; }
    @Override public int getIntrinsicHeight() { return size; }
}
