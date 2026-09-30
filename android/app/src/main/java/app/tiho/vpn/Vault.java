package app.tiho.vpn;
import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
final class Vault {
    private final Context ctx;
    Vault(Context c) { ctx=c; }
    private SecretKey key() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore"); ks.load(null);
        if (!ks.containsAlias("tiho")) {
            KeyGenerator g=KeyGenerator.getInstance("AES", "AndroidKeyStore");
            g.init(new KeyGenParameterSpec.Builder("tiho", KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes("GCM").setEncryptionPaddings("NoPadding").build()); g.generateKey();
        }
        return (SecretKey)ks.getKey("tiho",null);
    }
    String get(String name) throws Exception {
        String s=ctx.getSharedPreferences("vault",0).getString(name,null); if(s==null)return "";
        String[] p=s.split(":"); Cipher c=Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(p[0],2)));
        return new String(c.doFinal(Base64.decode(p[1],2)),java.nio.charset.StandardCharsets.UTF_8);
    }
    void put(String name,String value) throws Exception {
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE,key());
        String s=Base64.encodeToString(c.getIV(),2)+":"+Base64.encodeToString(c.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)),2);
        if(!ctx.getSharedPreferences("vault",0).edit().putString(name,s).commit())throw new Exception("Не удалось сохранить данные");
    }
}
