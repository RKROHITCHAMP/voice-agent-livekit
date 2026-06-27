# Twilio + LiveKit SIP setup (for warm transfer)

The warm transfer dials a real phone through a **Twilio Elastic SIP Trunk**
that is registered with LiveKit as an **outbound trunk**. You only need this for
the transfer feature — booking, monitoring and take-over work without it.

## 1. Create a Twilio Elastic SIP Trunk

1. Sign in to the [Twilio Console](https://console.twilio.com).
2. Go to **Elastic SIP Trunking → Trunks → Create new trunk**.
3. Under **Termination**, set a **Termination SIP URI**, e.g.
   `your-trunk.pstn.twilio.com`.
4. Add **Credential** authentication (create a SIP credential list with a
   username + password) OR allow LiveKit's IPs via an IP Access Control List.
   Credentials are simpler.
5. **Enable transfers**: in the trunk's **Features** section, set
   **Call Transfer (SIP REFER) → Enabled** and tick **Enable PSTN Transfer**.
   (Required for `MoveParticipant`/REFER-based handoff to work.)

## 2. Register the trunk with LiveKit

Install the [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup/) and
authenticate (`lk cloud auth`).

Create an outbound trunk config file `outbound-trunk.json`:

```json
{
  "trunk": {
    "name": "Twilio outbound",
    "address": "your-trunk.pstn.twilio.com",
    "numbers": ["+1XXXXXXXXXX"],
    "auth_username": "your_sip_username",
    "auth_password": "your_sip_password"
  }
}
```

Register it:

```bash
lk sip outbound create outbound-trunk.json
# -> prints a trunk id like  ST_xxxxxxxxxxxx
```

Put that id in `backend/.env`:

```bash
SIP_OUTBOUND_TRUNK_ID=ST_xxxxxxxxxxxx
HUMAN_AGENT_NUMBER=+15105550123   # the human agent's phone, E.164
```

## 3. (Twilio trial accounts)

On a free trial you can **only call numbers you've verified**. Add the human
agent's number under **Phone Numbers → Verified Caller IDs** first, or upgrade
the account.

## 4. Test

With the worker running, start a call and say "I'd like to speak to a person."
The agent should dial `HUMAN_AGENT_NUMBER`, read the briefing, and connect you
on accept (press **1**) or apologise on decline (press **2**).

## References
- LiveKit — SIP trunk setup: https://docs.livekit.io/telephony/start/sip-trunk-setup/
- LiveKit — Agent-assisted (warm) transfer: https://docs.livekit.io/telephony/features/transfers/warm/
- LiveKit — Call forwarding (SIP REFER): https://docs.livekit.io/telephony/features/transfers/cold/
- Twilio — Call Transfer via SIP REFER: https://www.twilio.com/docs/sip-trunking/call-transfer
