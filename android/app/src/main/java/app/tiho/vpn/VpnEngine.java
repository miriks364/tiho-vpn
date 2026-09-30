package app.tiho.vpn;
import android.content.Context;
import com.wireguard.android.backend.*;
final class VpnEngine {
    static GoBackend backend;
    static volatile Tunnel.State state=Tunnel.State.DOWN;
    static final Tunnel tunnel=new Tunnel(){ public String getName(){return "tiho";} public State getState(){return state;} public void onStateChange(State s){state=s;} };
    static synchronized void init(Context ctx){if(backend==null)backend=new GoBackend(ctx.getApplicationContext());}
}
