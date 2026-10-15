package com.aircon.family;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Base64;
import org.junit.Test;
import static org.junit.Assert.*;

public class ServerIdentityTest {
    private static final String NONCE="0123456789abcdef0123456789abcdef", HOST="house.example";
    private static final long NOW=1760000000L;
    private final KeyPair key=pair();
    private static KeyPair pair() {
        try { KeyPairGenerator generator=KeyPairGenerator.getInstance("EC"); generator.initialize(new ECGenParameterSpec("secp256r1")); return generator.generateKeyPair(); }
        catch(Exception error) { throw new IllegalStateException(error); }
    }
    private static String fingerprint(KeyPair pair) throws Exception {
        return ServerIdentity.hex(MessageDigest.getInstance("SHA-256").digest(pair.getPublic().getEncoded()));
    }
    private static String sign(KeyPair pair,String message) throws Exception {
        Signature signer=Signature.getInstance("SHA256withECDSA"); signer.initSign(pair.getPrivate());
        signer.update(message.getBytes(StandardCharsets.UTF_8)); return Base64.getEncoder().encodeToString(signer.sign());
    }
    private ServerIdentity reply(int version,String algorithm,String fingerprint,String host,long issuedAt,String signature) {
        return new ServerIdentity(version,algorithm,Base64.getEncoder().encodeToString(key.getPublic().getEncoded()),fingerprint,host,issuedAt,signature);
    }
    private static void rejected(ServerIdentity identity) {
        try { identity.verify(NONCE,HOST,NOW); fail("Unverified server identity accepted"); } catch(IllegalArgumentException expected) {}
    }
    @Test public void aFreshSignatureOverOurNonceAndHostIsAccepted() throws Exception {
        String fingerprint=fingerprint(key);
        assertEquals(64,fingerprint.length());
        assertEquals(fingerprint,reply(1,"ES256",fingerprint,HOST,NOW-5,sign(key,ServerIdentity.message(NONCE,HOST,NOW-5))).verify(NONCE,HOST,NOW));
        assertEquals(fingerprint,reply(1,"ES256",fingerprint,HOST,NOW+600,sign(key,ServerIdentity.message(NONCE,HOST,NOW+600))).verify(NONCE,HOST,NOW));
    }
    @Test public void anotherHostOrNonceIsRejectedEvenWithAValidSignature() throws Exception {
        String fingerprint=fingerprint(key);
        rejected(reply(1,"ES256",fingerprint,"other.example",NOW,sign(key,ServerIdentity.message(NONCE,"other.example",NOW))));
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,sign(key,ServerIdentity.message(NONCE,"other.example",NOW))));
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,sign(key,ServerIdentity.message("ffffffffffffffffffffffffffffffff",HOST,NOW))));
        rejected(reply(1,"ES256",fingerprint,"",NOW,sign(key,ServerIdentity.message(NONCE,"",NOW))));
    }
    @Test public void staleOrFutureIssueTimesAreRejected() throws Exception {
        String fingerprint=fingerprint(key);
        rejected(reply(1,"ES256",fingerprint,HOST,NOW-601,sign(key,ServerIdentity.message(NONCE,HOST,NOW-601))));
        rejected(reply(1,"ES256",fingerprint,HOST,NOW+601,sign(key,ServerIdentity.message(NONCE,HOST,NOW+601))));
        rejected(reply(1,"ES256",fingerprint,HOST,0,sign(key,ServerIdentity.message(NONCE,HOST,0))));
        rejected(reply(1,"ES256",fingerprint,HOST,Long.MIN_VALUE,sign(key,ServerIdentity.message(NONCE,HOST,Long.MIN_VALUE))));
    }
    @Test public void tamperedSignatureOtherKeyFingerprintMismatchAlgorithmAndVersionAreRejected() throws Exception {
        String fingerprint=fingerprint(key), message=ServerIdentity.message(NONCE,HOST,NOW), signature=sign(key,message);
        byte[] bytes=Base64.getDecoder().decode(signature); bytes[bytes.length-1]^=1;
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,Base64.getEncoder().encodeToString(bytes)));
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,"not base64!"));
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,""));
        KeyPair other=pair();
        rejected(reply(1,"ES256",fingerprint,HOST,NOW,sign(other,message)));
        rejected(new ServerIdentity(1,"ES256",Base64.getEncoder().encodeToString(other.getPublic().getEncoded()),fingerprint,HOST,NOW,sign(other,message)));
        rejected(reply(1,"ES256",fingerprint(other),HOST,NOW,signature));
        rejected(reply(1,"ES256",fingerprint.toUpperCase(),HOST,NOW,signature));
        rejected(reply(1,"RS256",fingerprint,HOST,NOW,signature));
        rejected(reply(1,"",fingerprint,HOST,NOW,signature));
        rejected(reply(2,"ES256",fingerprint,HOST,NOW,signature));
        rejected(reply(0,"ES256",fingerprint,HOST,NOW,signature));
        rejected(new ServerIdentity(1,"ES256","",fingerprint,HOST,NOW,signature));
        rejected(new ServerIdentity(1,"ES256","AAAA",ServerIdentity.hex(MessageDigest.getInstance("SHA-256").digest(new byte[3])),HOST,NOW,signature));
    }
    @Test public void expectedHostNonceAndDisplayFollowTheServerContract() {
        assertEquals("house.example",ServerIdentity.expectedHost("https://House.example"));
        assertEquals("house.example",ServerIdentity.expectedHost("https://house.example:443"));
        assertEquals("house.example:8443",ServerIdentity.expectedHost("https://house.example:8443"));
        assertEquals("127.0.0.1:8765",ServerIdentity.expectedHost("http://127.0.0.1:8765"));
        assertEquals("ab12 cd34 ef56 7890",ServerIdentity.display("ab12cd34ef567890ffffffffffffffff"));
        assertEquals("ab12 cd",ServerIdentity.display("ab12cd"));
        assertTrue(ServerIdentity.nonce(new SecureRandom()).matches("[0-9a-f]{32}"));
        assertNotEquals(ServerIdentity.nonce(new SecureRandom()),ServerIdentity.nonce(new SecureRandom()));
        assertEquals("aircon-central-identity\n"+NONCE+"\nhouse.example\n1760000000",ServerIdentity.message(NONCE,HOST,NOW));
    }
}
