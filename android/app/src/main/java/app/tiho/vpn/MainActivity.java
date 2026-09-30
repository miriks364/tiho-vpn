package app.tiho.vpn;
import android.app.*;
import android.os.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.ColorDrawable;
import android.view.*;
import android.view.animation.*;
import android.widget.*;
import com.wireguard.android.backend.*;
import com.wireguard.config.Config;
import com.wireguard.crypto.KeyPair;
import com.wireguard.crypto.Key;
import org.json.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class MainActivity extends Activity {
    // Palette - Material Design 3 inspired
    final int BG=0xff0d1118, CARD=0xff161b22, CARD_LIGHT=0xff21262d, GREEN=0xff3fb950, ACCENT=0xff58a6ff, 
              RED=0xffa4161a, TEXT=0xffc9d1d9, TEXT_SECONDARY=0xff8b949e, BORDER=0xff30363d;
    LinearLayout root,body; TextView status,sub,connection; Button power; Vault vault;
    String url="",token="",privateKey="",expiry=""; int tab=0; boolean busy=false;
    ExecutorService io=Executors.newSingleThreadExecutor(); Handler handler=new Handler(Looper.getMainLooper());
    Runnable poll=new Runnable(){public void run(){refreshState();handler.postDelayed(this,1000);}};
    
    public void onCreate(Bundle b){super.onCreate(b); vault=new Vault(this); VpnEngine.init(this);
        try{url=vault.get("url"); token=vault.get("token"); privateKey=vault.get("key"); expiry=vault.get("expiry");
            if(privateKey.isEmpty()){privateKey=new KeyPair().getPrivateKey().toBase64();vault.put("key",privateKey);}}
        catch(Exception e){showAlert("Ошибка", "Хранилище недоступно. Очисти данные приложения и получи новый код доступа.");}
        render(); }
    
    protected void onResume(){super.onResume(); handler.post(poll);}
    protected void onPause(){super.onPause();handler.removeCallbacks(poll);}
    
    int dp(int n){return (int)(n*getResources().getDisplayMetrics().density);}
    
    GradientDrawable bg(int c,int r){GradientDrawable d=new GradientDrawable();d.setColor(c);d.setCornerRadius(dp(r));return d;}
    GradientDrawable bgStroke(int c, int s, int r){GradientDrawable d=new GradientDrawable();d.setColor(c);d.setCornerRadius(dp(r));d.setStroke(dp(s),BORDER);return d;}
    
    TextView text(String s,int size,int color){TextView t=new TextView(this);t.setText(s);t.setTextSize(size);t.setTextColor(color);t.setPadding(0,dp(6),0,dp(6));return t;}
    
    void gap(LinearLayout p,int h){View v=new View(this);p.addView(v,new LinearLayout.LayoutParams(1,dp(h)));}
    
    Button button(String s,boolean accent){
        Button b=new Button(this);b.setText(s);b.setAllCaps(false);b.setTextSize(16);
        b.setTextColor(accent?BG:TEXT);b.setTypeface(null,Typeface.BOLD);
        RippleDrawable ripple=new RippleDrawable(0x40ffffff,bg(accent?GREEN:CARD_LIGHT,12),null);
        b.setBackground(ripple);b.setMinHeight(dp(54));b.setPadding(dp(16),0,dp(16),0);
        return b;
    }
    
    void full(LinearLayout p,View v){p.addView(v,new LinearLayout.LayoutParams(-1,-2));}
    
    LinearLayout card(){LinearLayout c=new LinearLayout(this);c.setOrientation(1);c.setPadding(dp(20),dp(16),dp(20),dp(16));
        c.setBackground(bgStroke(CARD,1,16));full(body,c);return c;}
    void render(){
        root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(BG);root.setPadding(dp(16),dp(8),dp(16),0);setContentView(root);
        
        // Header
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(8),dp(16),dp(8),dp(12));
        TextView brand=text("тихо",42,TEXT);brand.setTypeface(null,Typeface.BOLD);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        TextView badge=text("v0.2",13,ACCENT);badge.setTypeface(null,Typeface.BOLD);header.addView(badge);full(root,header);
        
        // Navigation bar
        LinearLayout nav=new LinearLayout(this);nav.setBackground(bgStroke(CARD,1,0));
        String[] items={"Статус","Подписка","Настройки"};String[] icons={"📡","🔑","⚙️"};
        for(int i=0;i<3;i++){
            final int n=i;LinearLayout navItem=new LinearLayout(this);navItem.setOrientation(1);navItem.setGravity(Gravity.CENTER);
            navItem.setPadding(dp(8),dp(12),dp(8),dp(12));navItem.setBackground(tab==i?bg(CARD_LIGHT,0):null);
            TextView icon=text(icons[i],22,tab==i?GREEN:TEXT_SECONDARY);icon.setGravity(Gravity.CENTER);navItem.addView(icon);
            TextView label=text(items[i],10,tab==i?GREEN:TEXT_SECONDARY);label.setGravity(Gravity.CENTER);navItem.addView(label);
            nav.addView(navItem,new LinearLayout.LayoutParams(0,-1,1));
            navItem.setOnClickListener(v->{tab=n;render();});
        }full(root,nav);
        
        // Content
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=new LinearLayout(this);body.setOrientation(1);body.setPadding(dp(8),dp(16),dp(8),dp(16));scroll.addView(body);
        status=null; sub=null; power=null; connection=null;
        if(tab==0)home();else if(tab==1)subscription();else settings();
        
        refreshState();
    }
    void home(){
        gap(body,12);
        LinearLayout center=new LinearLayout(this);center.setOrientation(1);center.setGravity(Gravity.CENTER);full(body,center);
        
        // Status Card
        LinearLayout statusCard=new LinearLayout(this);statusCard.setOrientation(1);statusCard.setGravity(Gravity.CENTER);
        statusCard.setPadding(dp(20),dp(24),dp(20),dp(24));statusCard.setBackground(bgStroke(CARD_LIGHT,1,16));
        center.addView(statusCard,new LinearLayout.LayoutParams(-1,-2));
        
        // Power Button
        power=button("⏻",true);power.setTextSize(72);power.setTypeface(null,Typeface.BOLD);
        power.setBackground(new RippleDrawable(0x40ffffff,bg(GREEN,120),null));power.setMinHeight(dp(180));power.setMinWidth(dp(180));
        statusCard.addView(power,new LinearLayout.LayoutParams(dp(180),dp(180)));power.setOnClickListener(v->toggle());
        
        gap(statusCard,14);
        status=text("Не подключено",24,TEXT);status.setGravity(Gravity.CENTER);status.setTypeface(null,Typeface.BOLD);statusCard.addView(status);
        
        sub=text("Нажми для подключения",13,TEXT_SECONDARY);sub.setGravity(Gravity.CENTER);statusCard.addView(sub);
        
        gap(body,20);
        LinearLayout c=card();
        LinearLayout serverLabel=new LinearLayout(this);
        TextView serverIcon=text("🖥️",16,ACCENT);serverLabel.addView(serverIcon,new LinearLayout.LayoutParams(-2,-2));
        TextView serverTitle=text(" ТВОЙ СЕРВЕР",12,TEXT_SECONDARY);serverLabel.addView(serverTitle,new LinearLayout.LayoutParams(0,-2,1));
        full(c,serverLabel);
        
        connection=text(url.isEmpty()?"Не подключён":URI.create(url).getHost(),20,TEXT);connection.setTypeface(null,Typeface.BOLD);full(c,connection);
        
        LinearLayout details=new LinearLayout(this);details.setOrientation(1);
        TextView detail1=text("🔒 WireGuard • Защищённое соединение",13,ACCENT);full(details,detail1);
        TextView detail2=text("📱 1 устройство • Личный ключ на телефоне",13,GREEN);full(details,detail2);
        full(c,details);
        
        gap(body,20);
        TextView info=text("Выбери свой VPS в настройках. Код активации и все инструкции вышлет бот.",13,TEXT_SECONDARY);info.setLineSpacing(0,1.3f);full(body,info);
    }
    void subscription(){
        gap(body,8);
        full(body,text("💳 Твоя подписка",28,TEXT));full(body,text("Управляй своим доступом",13,TEXT_SECONDARY));
        gap(body,20);
        
        // Status Card
        LinearLayout c=card();
        LinearLayout statusLine=new LinearLayout(this);
        TextView statusIcon=text(token.isEmpty()?"⏸️":"✅",20,token.isEmpty()?ACCENT:GREEN);statusLine.addView(statusIcon,new LinearLayout.LayoutParams(-2,-2));
        TextView statusText=text(token.isEmpty()?" Не активирована":" Активна и работает",18,TEXT);statusText.setTypeface(null,Typeface.BOLD);statusLine.addView(statusText,new LinearLayout.LayoutParams(0,-2,1));
        full(c,statusLine);
        
        TextView subStatus=text(token.isEmpty()?"Купи доступ в Telegram-боте":"До "+until(),16,TEXT);subStatus.setTypeface(null,Typeface.BOLD);full(c,subStatus);
        
        if(!token.isEmpty()){
            TextView expInfo=text("Автоматическая проверка срока при подключении",12,TEXT_SECONDARY);full(c,expInfo);
        }
        
        gap(body,20);
        
        // Pricing
        LinearLayout pricing=new LinearLayout(this);pricing.setOrientation(1);pricing.setBackground(bgStroke(CARD,1,16));pricing.setPadding(dp(16),dp(12),dp(16),dp(12));full(body,pricing);
        
        addPricingOption(pricing,"30 дней","100 ⭐","Базовый");
        addPricingOption(pricing,"90 дней","270 ⭐","Популярный");
        addPricingOption(pricing,"365 дней","900 ⭐","Экономный");
        
        gap(body,20);
        
        Button activate=button("Активировать код",true);full(body,activate);activate.setOnClickListener(v->activate());
        gap(body,10);
        
        Button stars=button("Купить в Telegram · Stars",false);full(body,stars);stars.setOnClickListener(v->openBot());
        gap(body,20);
        
        TextView notice=text("📌 Одна подписка = один VPN-ключ на одном телефоне. Повторная покупка продлевает текущий доступ, не создаёт новый.",12,TEXT_SECONDARY);notice.setLineSpacing(0,1.3f);full(body,notice);
    }
    void addPricingOption(LinearLayout p, String period, String price, String label){
        LinearLayout opt=new LinearLayout(this);opt.setOrientation(0);opt.setGravity(Gravity.CENTER_VERTICAL);opt.setPadding(0,dp(8),0,dp(8));full(p,opt);
        TextView per=text(period,15,TEXT);per.setTypeface(null,Typeface.BOLD);opt.addView(per,new LinearLayout.LayoutParams(0,-2,1));
        TextView lbl=text(label,11,ACCENT);lbl.setTypeface(null,Typeface.BOLD);opt.addView(lbl,new LinearLayout.LayoutParams(-2,-2));
        TextView pr=text(price,14,GREEN);pr.setTypeface(null,Typeface.BOLD);opt.addView(pr,new LinearLayout.LayoutParams(-2,-2));
    }
    String until(){try{return new java.text.SimpleDateFormat("dd.MM.yyyy",java.util.Locale.getDefault()).format(new java.util.Date(Long.parseLong(expiry)*1000));}catch(Exception e){return "Проверяется при подключении";}}
    void settings(){
        gap(body,8);
        full(body,text("⚙️ Настройки",28,TEXT));full(body,text("Подключи свой VPS",13,TEXT_SECONDARY));
        gap(body,20);
        
        LinearLayout c=card();
        full(c,text("АДРЕС ВАШЕГО API",12,GREEN));full(c,text("HTTPS-адрес VPS сервера",12,TEXT_SECONDARY));
        
        EditText input=field("https://vpn.example.com",url);input.setInputType(17);full(c,input);
        
        gap(c,16);
        Button save=button("Сохранить API",true);full(c,save);
        save.setOnClickListener(v->{
            if(busy||VpnEngine.state==Tunnel.State.UP){info("Сначала отключи VPN и дождись завершения.");return;}
            try{
                String val=input.getText().toString().trim().replaceAll("/+$","");
                URI u=new URI(val);
                if(!"https".equals(u.getScheme())||u.getHost()==null||u.getRawUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||!(u.getPath().isEmpty()||u.getPath().equals("/")))throw new Exception();
                if(!val.equals(url)){vault.put("token","");vault.put("expiry","");token="";expiry="";}
                vault.put("url",val);url=val;info("✓ API сохранён. Перейди в «Подписка» для активации.");
            }catch(Exception ex){info("❌ Введи HTTPS-адрес без пути, без пароля и параметров.\nПример: https://vpn.example.com");}}
        });
        
        gap(body,20);
        
        LinearLayout sec=card();
        full(sec,text("🛡️ О БЕЗОПАСНОСТИ",12,ACCENT));
        TextView secText=text("VPN не скрывает личность, владелец сервера и сайты видят часть данных.\n\n" +
            "Ваш приватный ключ хранится локально и не передаётся. Доступ шифруется WireGuard.\n\n" +
            "IPv6 может не маршрутизироваться в этой версии.",12,TEXT_SECONDARY);
        secText.setLineSpacing(0,1.3f);full(sec,secText);
        
        gap(body,20);
        
        Button sysVPN=button("Настройки VPN Android",false);full(body,sysVPN);
        sysVPN.setOnClickListener(v->{
            try{startActivity(new Intent("android.settings.VPN_SETTINGS"));}
            catch(Exception e){info("Открой Настройки → Сеть → VPN");}
        });
        
        gap(body,16);
        full(body,text("тихо VPN 0.2.0 • β\nWireGuard® — товарный знак Jason A. Donenfeld",11,TEXT_SECONDARY));
    }
    EditText field(String hint,String value){
        EditText e=new EditText(this);e.setSingleLine(true);e.setTextColor(TEXT);e.setHintTextColor(TEXT_SECONDARY);
        e.setTextSize(15);e.setHint(hint);e.setText(value);e.setBackground(bgStroke(CARD_LIGHT,1,8));e.setPadding(dp(12),dp(10),dp(12),dp(10));return e;
    }
    void info(String s){if(!isFinishing())new AlertDialog.Builder(this).setMessage(s).setPositiveButton("Понятно",null).show();}
    void refreshState(){
        if(power==null)return;
        boolean up=VpnEngine.state==Tunnel.State.UP;
        power.setEnabled(!busy);power.setText(busy?"…":"⏻");
        power.setBackground(new RippleDrawable(0x40ffffff,bg(up?0x4f76d5b4:GREEN,100),null));
        status.setText(busy?"Подождите…":up?"🔒 Туннель включён":"📴 Не подключено");
        sub.setText(up?"Нажми для отключения":"Нажми для подключения");
    }
    interface Work{void run()throws Exception;}
    void work(Work w){if(busy)return;busy=true;refreshState();io.execute(()->{String error=null;try{w.run();}catch(Exception e){error=e.getMessage();}final String err=error;runOnUiThread(()->{busy=false;if(err!=null)info(err);render();});});}
    JSONObject api(String path,JSONObject payload)throws Exception{
        javax.net.ssl.HttpsURLConnection c=(javax.net.ssl.HttpsURLConnection)new URL(url+path).openConnection();c.setConnectTimeout(12000);c.setReadTimeout(15000);c.setInstanceFollowRedirects(false);c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");if(!token.isEmpty())c.setRequestProperty("Authorization","Bearer "+token);
        try{try(OutputStream os=c.getOutputStream()){os.write(payload.toString().getBytes(StandardCharsets.UTF_8));}int code=c.getResponseCode();if(code!=200){if(code==401||code==403)throw new Exception("Код недействителен или срок доступа истёк. Обратись к владельцу сервиса.");if(code==429)throw new Exception("Слишком много попыток. Попробуй через минуту.");throw new Exception("Сервер вернул ошибку "+code);}try(InputStream in=c.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=in.read(buf))!=-1){out.write(buf,0,n);if(out.size()>65536)throw new Exception("Некорректный ответ сервера");}return new JSONObject(out.toString("UTF-8"));}}catch(java.io.IOException e){throw new Exception("Сервер недоступен. Проверь интернет, адрес API и HTTPS-сертификат.");}finally{c.disconnect();}
    }
    void openBot(){
        if(url.isEmpty()){tab=2;render();info("Сначала укажи адрес API из сообщения бота или от владельца сервиса.");return;}
        work(()->{String link=api("/v1/public",new JSONObject()).optString("bot_url","");
            if(!link.matches("https://t\\.me/[A-Za-z0-9_]{5,32}"))throw new Exception("Бот ещё не подключён владельцем сервиса.");
            runOnUiThread(()->{try{startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(link)));}catch(Exception e){info("Установи Telegram или браузер, чтобы открыть бота.");}});
        });
    }
    void activate(){if(busy)return;if(url.isEmpty()){tab=2;render();info("Сначала укажи HTTPS-адрес своего API.");return;}if(VpnEngine.state==Tunnel.State.UP){info("Сначала отключи VPN.");return;}
        EditText input=field("Код от владельца сервиса","");input.setInputType(129);LinearLayout p=new LinearLayout(this);p.setPadding(dp(24),dp(8),dp(24),0);p.addView(input,new LinearLayout.LayoutParams(-1,-2));new AlertDialog.Builder(this).setTitle("Активировать доступ").setView(p).setNegativeButton("Отмена",null).setPositiveButton("Активировать",(d,w)->work(()->{JSONObject q=new JSONObject().put("code",input.getText().toString().trim()).put("public_key",new KeyPair(Key.fromBase64(privateKey)).getPublicKey().toBase64());JSONObject r=api("/v1/activate",q);String t=r.getString("token");vault.put("token",t);token=t;expiry=r.getString("expires_at");vault.put("expiry",expiry);})).show();
    }
    void toggle(){if(busy)return;if(VpnEngine.state==Tunnel.State.UP){work(()->VpnEngine.backend.setState(VpnEngine.tunnel,Tunnel.State.DOWN,null));return;}if(url.isEmpty()||token.isEmpty()){tab=1;render();info("Укажи сервер в настройках и активируй код доступа.");return;}Intent intent=android.net.VpnService.prepare(this);if(intent!=null)startActivityForResult(intent,7);else connect();}
    protected void onActivityResult(int r,int c,Intent data){super.onActivityResult(r,c,data);if(r==7){if(c==RESULT_OK)connect();else info("Разрешение на VPN не выдано.");}}
    void connect(){work(()->{JSONObject r=api("/v1/connect",new JSONObject());expiry=r.getString("expires_at");vault.put("expiry",expiry);
        String config="[Interface]\nPrivateKey = "+privateKey+"\nAddress = "+r.getString("address")+"\nDNS = "+r.getString("dns")+"\nMTU = 1280\n\n[Peer]\nPublicKey = "+r.getString("server_public_key")+"\nEndpoint = "+r.getString("endpoint")+"\nAllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n";
        Config parsed=Config.parse(new ByteArrayInputStream(config.getBytes(StandardCharsets.UTF_8)));VpnEngine.backend.setState(VpnEngine.tunnel,Tunnel.State.UP,parsed);
    });}
}
