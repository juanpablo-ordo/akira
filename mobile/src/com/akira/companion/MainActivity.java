package com.akira.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.ContactsContract.CommonDataKinds.Phone;
import android.speech.RecognizerIntent;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private final ExecutorService work = Executors.newSingleThreadExecutor();
    private static final int SPEECH = 1, CALL_CONTACT = 2, SMS_CONTACT = 3;
    private EditText invitation;
    private TextView status;
    private SharedPreferences prefs;
    private LinearLayout page;
    private volatile String lastRequest;
    private boolean working;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("companion", MODE_PRIVATE);
        ScrollView scroll = new ScrollView(this);
        page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        page.setPadding(pad, pad * 3, pad, pad * 2);
        page.setBackgroundColor(Color.rgb(244, 249, 251));
        scroll.addView(page);
        setContentView(scroll);
        TextView title = new TextView(this);
        title.setText("AKIRA Móvil");
        title.setTextSize(29);
        page.addView(title);
        status = new TextView(this);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        page.addView(status);
        showStatus(prefs.contains("token") ? "Teléfono emparejado" : "Empareja tu PC desde Ajustes de AKIRA.");
        invitation = new EditText(this);
        invitation.setSingleLine(true);
        invitation.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        invitation.setHint("Invitación de emparejamiento");
        invitation.setSaveEnabled(false);
        page.addView(invitation);
        add("Emparejar", () -> pair(invitation.getText().toString().trim()));
        add("Comprobar estado de la PC", () -> action("status"));
        add("Abrir página autorizada en la PC", () -> action("open_website"));
        add("Abrir programa autorizado en la PC", () -> action("open_application"));
        add("Consultar último recibo", this::receipt);
        add("Encender la PC en esta red", this::wake);
        add("Preparar mensaje a un contacto", () -> contact(SMS_CONTACT));
        add("Abrir marcador para un contacto", () -> contact(CALL_CONTACT));
        add("Dar instrucción por voz", this::speech);
        add("Olvidar emparejamiento en este teléfono", () -> new AlertDialog.Builder(this)
                .setMessage("El acceso concedido se revoca desde AKIRA en la PC. ¿Eliminar la conexión de este teléfono?")
                .setNegativeButton("Cancelar", null).setPositiveButton("Eliminar", (dialog, which) -> {
                    if (working) return;
                    prefs.edit().remove("address").remove("pin").remove("token").remove("iv").apply();
                    lastRequest = null;
                    showStatus("Conexión eliminada de este teléfono.");
                }).show());
    }

    private void add(String label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(v -> action.run());
        page.addView(button);
    }

    private void showStatus(String text) { status.setText(text); }
    private interface Job { String run() throws Exception; }
    private void run(String progress, Job job) {
        if (working) return;
        working = true;
        showStatus(progress);
        work.submit(() -> {
            String result;
            try { result = job.run(); }
            catch (javax.net.ssl.SSLException e) { result = "No se verificó la identidad de la PC. Revisa el emparejamiento."; }
            catch (java.net.SocketTimeoutException | java.net.ConnectException e) { result = "La PC o el servicio móvil no responde en esta red."; }
            catch (Exception e) { result = e.getMessage() == null ? "La acción no pudo completarse." : e.getMessage(); }
            final String message = result;
            runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) { working = false; showStatus(message); } });
        });
    }

    private void pair(String text) {
        String[] fields = text.split("\\|", -1);
        if (fields.length != 4 || !fields[0].equals("AKIRA1") || !fields[3].matches("[0-9]{8}")) {
            showStatus("Copia la invitación completa que aparece en la PC."); return;
        }
        invitation.setText("");
        run("Confirma el emparejamiento en la PC.", () -> {
            CompanionClient pc = new CompanionClient(fields[1], fields[2], "");
            JSONObject pair = pc.post("/pair", new JSONObject().put("code", fields[3]).put("name", Build.MODEL));
            JSONObject ticket = new JSONObject().put("id", pair.getString("id")).put("ticket", pair.getString("ticket"));
            long end = android.os.SystemClock.elapsedRealtime() + 115_000;
            while (android.os.SystemClock.elapsedRealtime() < end) {
                JSONObject response = pc.post("/pair/status", ticket);
                switch (response.getString("status")) {
                    case "APPROVED":
                        new CompanionClient(fields[1], fields[2], response.getString("authorization")).save(prefs);
                        return "Teléfono emparejado durante 30 días.";
                    case "REJECTED": return "La PC rechazó el emparejamiento.";
                    default: Thread.sleep(1250);
                }
            }
            return "La solicitud de emparejamiento caducó.";
        });
    }

    private void action(String name) {
        if (working) return;
        String request = UUID.randomUUID().toString();
        lastRequest = request;
        run("Enviando solicitud a la PC…", () -> CompanionClient.load(prefs).post("/action",
                new JSONObject().put("id", request).put("action", name)
                        .put("expires", System.currentTimeMillis() / 1000.0 + 65)).getString("status"));
    }

    private void receipt() {
        String request = lastRequest;
        if (request == null) { showStatus("Todavía no hay una solicitud de esta sesión."); return; }
        run("Buscando recibo…", () -> CompanionClient.load(prefs).post("/action/status",
                new JSONObject().put("id", request)).getString("status"));
    }

    private void wake() {
        EditText broadcast = new EditText(this), mac = new EditText(this);
        broadcast.setHint("IPv4 de difusión de tu red");
        mac.setHint("MAC de la tarjeta de red de tu PC");
        mac.setText(prefs.getString("wol_mac", ""));
        broadcast.setText(prefs.getString("wol_broadcast", ""));
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL); form.addView(broadcast); form.addView(mac);
        new AlertDialog.Builder(this).setTitle("Encender PC con Wake-on-LAN").setView(form)
                .setNegativeButton("Cancelar", null).setPositiveButton("Enviar", (dialog, which) -> {
                    String ip = broadcast.getText().toString().trim(), address = mac.getText().toString().trim();
                    String clean = address.replace(":", "").replace("-", "");
                    if (!CompanionClient.privateIp(ip) || !clean.matches("[0-9a-fA-F]{12}")) {
                        showStatus("Revisa la IPv4 privada de difusión y la dirección MAC."); return;
                    }
                    run("Enviando señal de encendido…", () -> {
                        CompanionClient.load(prefs);
                        byte[] packet = new byte[102];
                        Arrays.fill(packet, 0, 6, (byte) 255);
                        for (int i = 6; i < packet.length; i++) {
                            int offset = ((i - 6) % 6) * 2;
                            packet[i] = (byte) Integer.parseInt(clean.substring(offset, offset + 2), 16);
                        }
                        try (DatagramSocket socket = new DatagramSocket()) {
                            socket.setBroadcast(true);
                            socket.send(new DatagramPacket(packet, packet.length, InetAddress.getByName(ip), 9));
                        }
                        prefs.edit().putString("wol_mac", address).putString("wol_broadcast", ip).apply();
                        return "Señal enviada. Comprueba el estado de la PC después de que arranque.";
                    });
                }).show();
    }

    private void contact(int request) {
        try { startActivityForResult(new Intent(Intent.ACTION_PICK, Phone.CONTENT_URI), request); }
        catch (android.content.ActivityNotFoundException e) { showStatus("Android no encontró un selector de contactos."); }
    }

    private void speech() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-GT")
                .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                .putExtra(RecognizerIntent.EXTRA_PROMPT, "Indica qué quieres hacer.");
        try { startActivityForResult(intent, SPEECH); }
        catch (android.content.ActivityNotFoundException e) { showStatus("Este teléfono no ofrece reconocimiento de voz."); }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK || data == null) return;
        if (request == SPEECH) {
            ArrayList<String> matches = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (matches == null || matches.isEmpty()) return;
            String words = matches.get(0).toLowerCase(Locale.ROOT);
            if (words.contains("enciende")) wake();
            else if (words.contains("banca") || words.contains("página")) action("open_website");
            else if (words.contains("aplicación") || words.contains("programa")) action("open_application");
            else if (words.contains("mensaje")) contact(SMS_CONTACT);
            else if (words.contains("llama")) contact(CALL_CONTACT);
            else if (words.contains("estado")) action("status");
            else showStatus("Elige una acción en la pantalla.");
            return;
        }
        Uri uri = data.getData();
        if (uri == null) return;
        try (Cursor row = getContentResolver().query(uri, new String[]{Phone.DISPLAY_NAME, Phone.NUMBER}, null, null, null)) {
            if (row == null || !row.moveToFirst()) { showStatus("No hay un número seleccionado."); return; }
            confirmContact(request, row.getString(0), row.getString(1));
        } catch (RuntimeException e) { showStatus("Android no concedió acceso al contacto elegido."); }
    }

    private void confirmContact(int request, String name, String number) {
        boolean sms = request == SMS_CONTACT;
        String recipient = name + " · " + number;
        EditText draft = new EditText(this);
        draft.setHint("Escribe el borrador");
        AlertDialog.Builder dialog = new AlertDialog.Builder(this).setTitle(sms ? "Preparar mensaje" : "Abrir marcador")
                .setMessage(recipient).setNegativeButton("Cancelar", null);
        if (sms) dialog.setView(draft);
        dialog.setPositiveButton(sms ? "Abrir borrador" : "Confirmar número", (box, which) -> {
            Intent handoff = new Intent(sms ? Intent.ACTION_SENDTO : Intent.ACTION_DIAL,
                    Uri.fromParts(sms ? "smsto" : "tel", number, null));
            if (sms) handoff.putExtra("sms_body", draft.getText().toString());
            try { startActivity(handoff); showStatus(sms ? "Borrador abierto en Mensajes." : "Marcador abierto."); }
            catch (android.content.ActivityNotFoundException e) { showStatus("Android no encontró una aplicación para completar la acción."); }
        }).show();
    }

    @Override protected void onDestroy() {
        work.shutdownNow();
        super.onDestroy();
    }
}
