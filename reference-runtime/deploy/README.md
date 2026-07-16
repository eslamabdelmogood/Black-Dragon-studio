# Deploying Nomad Sentinel on Alibaba Cloud

Two Alibaba Cloud services are used regardless of which hosting option
you pick below:

1. **Compute** — hosts the always-on Flask API + dashboard
   (`src/nomad_sentinel/runtime/api/server.py`), unmodified either way.
2. **OSS** — durable telemetry/decision-log storage, written by
   [`alibaba_oss_telemetry.py`](alibaba_oss_telemetry.py) whenever
   Stallion mode (Qwen Cloud) produces a decision.

## Option A: Function Compute (recommended — genuinely free tier)

Unlike ECS, Function Compute's free tier (roughly 1M requests/month and
400,000 GB-seconds/month, resets monthly — check the current numbers on
the [FC pricing page](https://www.aliyun.com/product/fc), they do
change) isn't a time-limited trial, and a hackathon demo won't come
close to that ceiling. No idle VM, no ongoing cost. See
[`fc/`](fc/) for the full setup — short version:

```bash
npm install -g @serverless-devs/s
s config add                                   # paste your (rotated) AccessKey ID/Secret

cp deploy/env.production.example deploy/env.production
nano deploy/env.production                     # fill in QWEN_API_KEY, ALIBABA_OSS_* values

bash deploy/fc/deploy.sh
```

`s deploy` prints an HTTP trigger URL when it finishes — that's your
live dashboard/API endpoint, running the exact same `server.py` as the
ECS path below, just hosted serverlessly. Then produce your deployment
proof the same way as Option B, step 4.

One caveat worth knowing up front: Alibaba Cloud generally requires a
verified payment method on file to activate any service, free tier
included — you won't be charged while under the free quota, but you
likely can't skip linking a card/PayPal entirely.

## Option B: ECS (if you'd rather run a persistent VM)

**1. On your own machine** — install and configure the `aliyun` CLI,
then create the bucket and the instance (fill in your own security
group / vswitch IDs, shown in the console under your default VPC):

```bash
aliyun configure                                    # region: ap-southeast-1 (or wherever your Qwen workspace is)
aliyun oss mb oss://nomad-sentinel-telemetry --region ap-southeast-1
aliyun ecs CreateInstance \
  --RegionId ap-southeast-1 \
  --ImageId ubuntu_22_04_x64_20G_alibase \
  --InstanceType ecs.t6-c1m2.large \
  --SecurityGroupId <your-sg-id> \
  --VSwitchId <your-vswitch-id> \
  --InstanceName nomad-sentinel-api
```

Then open port 8765 in that instance's security group (console →
Security Groups → Add Rule), and confirm SSH access. Note this option
is **not free** — a small instance runs roughly $0.02–0.05/hour, so a
day or two of demo/recording time is well under a dollar, but it's not
$0 the way Option A is.

**2. SSH into the instance and clone the repo:**

```bash
ssh root@<ecs-public-ip>
git clone <your-repo-url> nomad-sentinel && cd nomad-sentinel
cp deploy/env.production.example deploy/env.production
nano deploy/env.production
```

**3. Run the setup script:**

```bash
bash deploy/setup.sh
```

This installs dependencies, installs and starts the systemd service
([`nomad-sentinel.service`](nomad-sentinel.service)), and prints the
dashboard URL.

**4. Produce your deployment proof (same for either option):**

```bash
bash deploy/verify.sh
```

This runs a real 400-step simulation, uploads the resulting log to your
OSS bucket via [`alibaba_oss_telemetry.py`](alibaba_oss_telemetry.py),
and lists the bucket contents to confirm the object actually landed.
That terminal output — or a console screenshot of the same object under
**OSS → your bucket → runs/** — is what goes in the submission as Proof
of Alibaba Cloud Deployment, alongside a link to
[`alibaba_oss_telemetry.py`](alibaba_oss_telemetry.py) itself.

## What's here

| File | Purpose |
|---|---|
| [`fc/`](fc/) | Function Compute deployment (Option A) — `s.yaml`, `bootstrap`, `deploy.sh` |
| [`setup.sh`](setup.sh) | ECS setup (Option B) — installs deps, systemd service |
| [`verify.sh`](verify.sh) | Either option — produces the actual proof artifact |
| [`nomad-sentinel.service`](nomad-sentinel.service) | ECS systemd unit |
| [`alibaba_oss_telemetry.py`](alibaba_oss_telemetry.py) | Real `oss2` SDK client — the code file referenced as proof of Alibaba Cloud usage |
| [`env.production.example`](env.production.example) | Copy to `env.production`, fill in, never commit |
