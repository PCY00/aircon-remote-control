package com.aircon.family;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;
import java.util.Locale;

/** The server's signed answer to the app's nonce, checked with plain Java so every rule runs in JVM tests. */
final class ServerIdentity {
    static final String PATH="/v1/server-identity", ALGORITHM="ES256";
    static final int VERSION=1;
    /** Clock difference tolerated between the phone and the server, in seconds. */
    static final long MAX_SKEW=600;
    final int version;
    final String algorithm, publicKey, fingerprint, host, signature;
    final long issuedAt;
    ServerIdentity(int version,String algorithm,String publicKey,String fingerprint,String host,long issuedAt,String signature) {
        this.version=version; this.algorithm=algorithm; this.publicKey=publicKey; this.fingerprint=fingerprint;
        this.host=host; this.issuedAt=issuedAt; this.signature=signature;
    }
    /** Returns the verified key fingerprint; any failed rule is an IllegalArgumentException so no token follows. */
    String verify(String nonce,String expectedHost,long now) {
        try {
            if(version!=VERSION || !ALGORITHM.equals(algorithm) || !expectedHost.equals(host)) throw new IllegalArgumentException();
            if(issuedAt<now-MAX_SKEW || issuedAt>now+MAX_SKEW) throw new IllegalArgumentException();
            byte[] der=Base64.getDecoder().decode(publicKey);
            if(!hex(MessageDigest.getInstance("SHA-256").digest(der)).equals(fingerprint)) throw new IllegalArgumentException();
            PublicKey key=KeyFactory.getInstance("EC").generatePublic(new X509EncodedKeySpec(der));
            if(!(key instanceof ECPublicKey) || ((ECPublicKey)key).getParams().getCurve().getField().getFieldSize()!=256)
                throw new IllegalArgumentException();
            Signature verifier=Signature.getInstance("SHA256withECDSA"); verifier.initVerify(key);
            verifier.update(message(nonce,host,issuedAt).getBytes(StandardCharsets.UTF_8));
            if(!verifier.verify(Base64.getDecoder().decode(signature))) throw new IllegalArgumentException();
            return fingerprint;
        } catch(GeneralSecurityException|RuntimeException error) { throw new IllegalArgumentException("server identity invalid"); }
    }
    static String message(String nonce,String host,long issuedAt) { return "aircon-central-identity\n"+nonce+"\n"+host+"\n"+issuedAt; }
    static String nonce(SecureRandom random) { byte[] bytes=new byte[16]; random.nextBytes(bytes); return hex(bytes); }
    /** The Host header the phone sends: lowercase, with the port only when it is not the scheme default. */
    static String expectedHost(String origin) {
        URI uri=URI.create(origin); int port=uri.getPort();
        boolean standard=port<0 || port==("https".equals(uri.getScheme()) ? 443 : 80);
        return uri.getHost().toLowerCase(Locale.ROOT)+(standard ? "" : ":"+port);
    }
    /** The first 16 hex characters in groups of four, the form the owner compares with the server's own output. */
    static String display(String fingerprint) {
        StringBuilder text=new StringBuilder();
        for(int i=0;i<16 && i<fingerprint.length();i+=4) { if(i>0) text.append(' '); text.append(fingerprint,i,Math.min(i+4,fingerprint.length())); }
        return text.toString();
    }
    static String hex(byte[] bytes) {
        StringBuilder text=new StringBuilder(); for(byte b:bytes) text.append(String.format("%02x",b&255)); return text.toString();
    }
}
