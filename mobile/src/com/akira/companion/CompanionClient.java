package com.akira.companion;

import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Locale;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import org.json.JSONObject;

final class CompanionClient {
    private static final String KEY_ALIAS = "akira_lan_companion";
    private static final int MAX_RESPONSE = 4096;
    final URL base;
    final byte[] fingerprint;
    final String authorization;

    CompanionClient(String address, String pin, String authorization) throws Exception {
        base = new URL(address);
        if (!base.getProtocol().equals("https") || base.getUserInfo() != null
                || base.getPort() != 48225 || !base.getFile().isEmpty() || base.getRef() != null
                || !privateIp(base.getHost()) || !pin.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("El emparejamiento requiere HTTPS y la IPv4 privada que muestra AKIRA.");
        }
        fingerprint = new byte[32];
        for (int i = 0; i < fingerprint.length; i++) {
            fingerprint[i] = (byte) Integer.parseInt(pin.substring(2 * i, 2 * i + 2), 16);
        }
        this.authorization = authorization;
    }

    static boolean privateIp(String ip) {
        if (!ip.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}")) return false;
        String[] parts = ip.split("\\.");
        for (String octet : parts) if (Integer.parseInt(octet) > 255) return false;
        int first = Integer.parseInt(parts[0]), second = Integer.parseInt(parts[1]);
        return first == 10 || (first == 172 && second >= 16 && second <= 31)
                || (first == 192 && second == 168);
    }

    JSONObject post(String endpoint, JSONObject message) throws Exception {
        SSLContext ssl = SSLContext.getInstance("TLS");
        X509TrustManager pinned = new X509TrustManager() {
            @Override public void checkServerTrusted(X509Certificate[] chain, String auth) throws CertificateException {
                if (chain == null || chain.length != 1) throw new CertificateException("Certificado imprevisto.");
                try {
                    chain[0].checkValidity();
                    byte[] digest = MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded());
                    if (!MessageDigest.isEqual(digest, fingerprint)) throw new CertificateException("Huella de la PC distinta.");
                } catch (java.security.GeneralSecurityException e) {
                    throw new CertificateException("No se verificó la identidad de la PC.", e);
                }
            }
            @Override public void checkClientTrusted(X509Certificate[] chain, String auth) throws CertificateException {
                throw new CertificateException("Autenticación de cliente TLS no habilitada.");
            }
            @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
        };
        ssl.init(null, new TrustManager[]{pinned}, null);
        HttpsURLConnection connection = (HttpsURLConnection) new URL(base, endpoint).openConnection();
        connection.setSSLSocketFactory(ssl.getSocketFactory());
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(3500);
        connection.setReadTimeout(6000);
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        if (!authorization.isEmpty()) connection.setRequestProperty("Authorization", "Bearer " + authorization);
        connection.setDoOutput(true);
        byte[] request = message.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(request.length);
        try {
            try (OutputStream out = connection.getOutputStream()) { out.write(request); }
            int code = connection.getResponseCode();
            if (code < 200 || code >= 300) {
                String messageText = code == 403 ? "Solicitud rechazada o emparejamiento caducado."
                        : "El servicio móvil respondió con un error (" + code + ").";
                throw new IOException(messageText);
            }
            try (InputStream in = connection.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] chunk = new byte[1024];
                for (int size; (size = in.read(chunk)) != -1;) {
                    if (out.size() + size > MAX_RESPONSE) throw new IOException("Respuesta demasiado grande.");
                    out.write(chunk, 0, size);
                }
                return new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
            }
        } finally {
            connection.disconnect();
        }
    }

    static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator keys = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        keys.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return keys.generateKey();
    }

    void save(SharedPreferences prefs) throws Exception {
        StringBuilder pin = new StringBuilder();
        for (byte value : fingerprint) pin.append(String.format(Locale.ROOT, "%02x", value & 255));
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        String host = base.toString();
        cipher.updateAAD((host + "|" + pin).getBytes(StandardCharsets.UTF_8));
        byte[] data = cipher.doFinal(authorization.getBytes(StandardCharsets.UTF_8));
        prefs.edit().putString("address", host).putString("pin", pin.toString())
                .putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                .putString("token", Base64.encodeToString(data, Base64.NO_WRAP)).apply();
    }

    static CompanionClient load(SharedPreferences prefs) throws Exception {
        String host = prefs.getString("address", ""), pin = prefs.getString("pin", "");
        if (host.isEmpty()) throw new IllegalStateException("Empareja el teléfono con AKIRA en la PC.");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(),
                new GCMParameterSpec(128, Base64.decode(prefs.getString("iv", ""), Base64.NO_WRAP)));
        cipher.updateAAD((host + "|" + pin).getBytes(StandardCharsets.UTF_8));
        String token = new String(cipher.doFinal(Base64.decode(prefs.getString("token", ""), Base64.NO_WRAP)),
                StandardCharsets.UTF_8);
        return new CompanionClient(host, pin, token);
    }
}
