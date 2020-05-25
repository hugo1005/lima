const client = new WebSocket(process.env.VUE_APP_BACKEND_WEBSOCKET_URL)

export default function createWebSocketPlugin() {
    return store => {
        client.onopen = function() {
            store.dispatch('backend/connectionOpened')
        }

        client.onerror = function(event) {
            store.dispatch('backend/connectionError', event)
        }
        
        client.onmessage = function(event) {  
            let msg = JSON.parse(event.data)
            if(msg.type == 'LOBS') {
                store.dispatch('backend/updateLimitBook', msg.data)
            }
            if(msg.type == 'MBS') {
                store.dispatch('backend/updateMarketBook', msg.data)
            }
            else if(msg.type == 'tape') {
                store.dispatch('backend/updateTape', msg.data)
            }
            else if(msg.type == 'traders') {
                store.dispatch('backend/updateTraders', msg.data)
            }
            else if(msg.type == 'current_time') {
                store.dispatch('backend/updateTime', msg.data)
            } 
            // TODO: Implement the overall admin dashboard
            // else if(msg.type == 'risk') {
            //     store.dispatch('backend/updateRisk', msg.data)
            // }
            // else if(msg.type == 'pnl') {
            //     store.dispatch('backend/updatePnL', msg.data)
            // }
        }

        // An example for communicating back:
        // Link: http://iamnotmyself.com/2020/02/14/implementing-websocket-plugins-for-vuex/
        // Link: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications
        // store.subscribe((mutation, state) => {
        //     if (state.chat.connected && mutation.type === 'chat/SEND_MESSAGE')
        //       client.invoke('SendMessage', null, message);
        //   });
    }
}