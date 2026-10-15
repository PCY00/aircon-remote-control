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
            case "minus": path(canvas,5,12,19,12); break;
            case "snowflake":
                // Six identical arms, each a spoke with a small chevron near its tip.
                for (int arm = 0; arm < 6; arm++) {
                    int turned = canvas.save(); canvas.rotate(arm * 60f, 12, 12);
                    path(canvas,12,12,12,3); path(canvas,9.8f,5,12,7.2f,14.2f,5);
                    canvas.restoreToCount(turned);
                }
                break;
            case "auto":
                // Two arrows chasing each other: the automatic cycle.
                canvas.drawArc(5,5,19,19,200,140,false,paint); path(canvas,19.6f,6.8f,18.6f,9.6f,16f,8.1f);
                canvas.drawArc(5,5,19,19,20,140,false,paint); path(canvas,4.4f,17.2f,5.4f,14.4f,8f,15.9f); break;
            case "droplet": {
                Path drop = new Path(); drop.moveTo(12,3); drop.cubicTo(9,7,5,10.5f,5,14.5f);
                drop.arcTo(5,7.5f,19,21.5f,180,-180,false); drop.cubicTo(19,10.5f,15,7,12,3);
                canvas.drawPath(drop,paint); break;
            }
            case "wind":
                path(canvas,3,9,15,9); canvas.drawArc(12.5f,4,17.5f,9,90,-270,false,paint);
                path(canvas,3,13,19,13);
                path(canvas,3,17,13,17); canvas.drawArc(10.5f,17,15.5f,22,270,270,false,paint); break;
            case "power": canvas.drawArc(5,5,19,19,-60,300,false,paint); path(canvas,12,3,12,11); break;
            case "aircon":
                canvas.drawRoundRect(3,5,21,13,2,2,paint); path(canvas,6,10,18,10);
                path(canvas,8,16,7,20); path(canvas,12,16,12,20); path(canvas,16,16,17,20); break;
            case "shield": path(canvas,12,3,19,6,19,12,12,21,5,12,5,6,12,3); path(canvas,9,12,11,14,15,10); break;
            case "expand": path(canvas,6,9,12,15,18,9); break;
            case "thermometer":
                canvas.drawRoundRect(9.5f,3,14.5f,15,2.5f,2.5f,paint); canvas.drawCircle(12,18,3.5f,paint); path(canvas,12,8,12,18); break;
            case "bulb":
                canvas.drawArc(6,3,18,15,150,240,false,paint); path(canvas,7.6f,12,9.5f,15.5f,9.5f,17,14.5f,17,14.5f,15.5f,16.4f,12);
                path(canvas,10,20,14,20); break;
            case "plug":
                path(canvas,9,3,9,8); path(canvas,15,3,15,8); path(canvas,6,8,18,8,18,12);
                canvas.drawArc(6,6,18,18,0,180,false,paint); path(canvas,6,12,6,8); path(canvas,12,18,12,21); break;
            case "motion":
                canvas.drawCircle(13,4.5f,1.8f,paint); path(canvas,9,10,12,8,15,10,17,12); path(canvas,12,8,11,14,14,17,14,21);
                path(canvas,11,14,8,17,6,17); break;
            case "wifi_off":
                canvas.drawArc(2,4,22,24,220,100,false,paint); canvas.drawArc(6,9,18,21,220,100,false,paint);
                canvas.drawCircle(12,18,1,paint); path(canvas,4,4,20,20); break;
            case "battery":
                canvas.drawRoundRect(3,8,19,16,2,2,paint); path(canvas,21,11,21,13); path(canvas,6,11,6,13); break;
            case "star": case "star_filled": {
                Path star=new Path();
                for(int point=0;point<10;point++) {
                    double angle=Math.toRadians(-90+point*36); float radius=point%2==0 ? 9f : 4f;
                    float x=12+(float)(radius*Math.cos(angle)), y=12.5f+(float)(radius*Math.sin(angle));
                    if(point==0) star.moveTo(x,y); else star.lineTo(x,y);
                }
                star.close();
                if(name.equals("star_filled")) { paint.setStyle(Paint.Style.FILL_AND_STROKE); canvas.drawPath(star,paint); paint.setStyle(Paint.Style.STROKE); }
                else canvas.drawPath(star,paint);
                break;
            }
            case "moon": canvas.drawArc(4,4,20,20,60,250,false,paint); canvas.drawArc(9,2,21,14,95,170,false,paint); break;
            case "check": path(canvas,5,12,10,17,19,7); break;
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
