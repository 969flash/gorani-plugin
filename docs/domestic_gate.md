# 국내 서버 문지기 (server_gate)

컨텍스트·등고선 팩(Oracle 춘천 버킷) 앞에 VM 하나를 세워 규칙에 맞는 요청만 내주는 절차.

## 구조

```
플러그인 ──HTTP──▶ 춘천 VM: nginx ──auth_request──▶ server_gate.py (한도 판정)
                         └──비공개 PAR──▶ Private 버킷
```

- 버킷은 Private로 둔다. VM만 PAR(인증 없이 읽는 비밀 주소)로 읽는다. PAR은 VM의 `/opt/udt/par`에만 있다.
- 매니페스트(HF, 공개)에는 VM 주소만 적힌다(`constants.DATA_DOMESTIC_BASE_URL`).
- 플러그인은 팩 요청에 `User-Agent: UrbanDesignTool/<버전>`과 `X-UDT-Client: <설치 ID>`를 붙인다. 403·404가 오면 매니페스트를 새로 읽어 한 번 다시 받는다.
- HTTP로 둔다. 파일 변조는 매니페스트(HTTPS)의 sha256으로 걸러진다. HTTPS가 필요하면 도메인을 붙이고 certbot을 쓴다.

현재(2026-10-14): VM `udt-gate`, `VM.Standard.E2.1.Micro`(이 계정은 A1 한도가 0), 공인 IP 150.230.249.1, VCN `udt-gate-vcn`, 알람 topic `udt-alerts`(bsh969flash@gmail.com). SSH 키 `~/.ssh/udt-gate.key`, PAR 만료 2027-10-01.

## 비정상 요청 기준

기준값은 `scripts/server_gate.py` 맨 위 상수에 있다. 하루는 한국 시간 자정에 초기화된다.

| 규칙 | 기준 | 사용자가 받는 응답 |
|---|---|---|
| 설치 하나가 하루에 받는 팩 | 60개 초과 | 429 (그날 끝까지) |
| 설치 하나가 같은 팩을 받는 횟수 | 하루 3회 초과 | 429 |
| IP 하나가 하루에 받는 팩 | 150개 초과 | 429 |
| IP 하나가 없는 팩 이름을 요청한 횟수 | 하루 20회 초과 | 그날 그 IP의 요청 전부 429 |
| IP 하나의 동시 연결 | 4개 초과 | 503 (nginx) |
| 설치 ID 없음 (프로그램이 아닌 요청) | 1건이라도 | 403 |

플러그인은 429를 받으면 "오늘 받을 수 있는 양을 넘었습니다" 문구를 띄운다. 한도 카운트는 메모리에만 있어서 서버를 재시작하면 0부터 다시 센다.

## 처음 세우기

`<IP>`는 VM의 공인 IP다. SSH 키는 `~/.ssh/udt-gate.key`, PAR은 `~/.oci/udt_gate_par`(권한 600)에 둔다. PAR은 비밀이라 화면·저장소·대화창에 내지 않는다.

1. **로그인한다.** 업로드 키에는 PAR·버킷 설정 권한이 없어서 브라우저 로그인(MFA)이 필요하다. 세션은 1시간 유지된다.
   ```
   oci session authenticate --profile-name SESSION --region ap-chuncheon-1
   ```
2. **PAR을 만들어 파일로 받는다.** 만료일은 달력에 적어 둔다.
   ```
   oci os preauth-request create --profile SESSION --auth security_token \
     -bn urbandesigntool-data --name udt-gate --access-type AnyObjectRead \
     --bucket-listing-action Deny --time-expires 2027-10-01T00:00:00Z \
     --query 'data."full-path"' --raw-output > ~/.oci/udt_gate_par && chmod 600 ~/.oci/udt_gate_par
   ```
3. **콘솔에서 VM을 만든다** (cloud.oracle.com, 리전 Chuncheon).
   - Compute → Instances → Create instance.
   - Image: Canonical Ubuntu 24.04.
   - Shape: `VM.Standard.A1.Flex` 1 OCPU·6 GB. "Out of capacity"가 나면 `VM.Standard.E2.1.Micro`를 쓴다. 둘 다 Always Free 표시가 있어야 한다.
   - Networking: 새 VCN·public subnet, "Assign a public IPv4 address"를 켠다.
   - SSH keys: "Generate a key pair for me" → Save private key. 받은 파일을 옮긴다:
     `mv ~/Downloads/ssh-key-*.key ~/.ssh/udt-gate.key && chmod 600 ~/.ssh/udt-gate.key`
   - Create. Running이 되면 Public IP를 적어 둔다.
   - 80번 포트 열기: 인스턴스 → Networking(Primary VNIC) → Subnet → Security → Default Security List → Add Ingress Rules → Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `80`.
4. **VM에 설치한다.**
   ```
   scp -i ~/.ssh/udt-gate.key scripts/server_gate.py ubuntu@<IP>:
   ssh -i ~/.ssh/udt-gate.key ubuntu@<IP> "sudo apt-get update && sudo apt-get install -y nginx && sudo python3 server_gate.py install $(cat ~/.oci/udt_gate_par)"
   ```
5. **확인한다.** 차례로 `200`·`403`·`404`가 나오면 정상이다.
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -H "X-UDT-Client: 0f8fad5b-d9cb-469f-a165-70867728950e" http://<IP>/11680_context.db.xz
   curl -s -o /dev/null -w "%{http_code}\n" http://<IP>/11680_context.db.xz
   curl -s -o /dev/null -w "%{http_code}\n" -H "X-UDT-Client: 0f8fad5b-d9cb-469f-a165-70867728950e" http://<IP>/99999_context.db.xz
   ```
6. **전환한다.**
   - `constants.DATA_DOMESTIC_BASE_URL = "http://<IP>/"`로 바꾸고 `python3 scripts/dev_deploy.py upload`(매니페스트가 VM 주소로 바뀐다).
   - HF 매니페스트가 바뀐 것을 확인한 뒤 버킷을 닫는다(로그인 1시간이 지났으면 1번부터).
     ```
     oci os bucket update --profile SESSION --auth security_token --name urbandesigntool-data --public-access-type NoPublicAccess
     ```
7. **알람을 건다.** Notifications topic `udt-alerts`(메일 구독 — 확인 메일의 링크를 눌러야 받는다)에 알람 둘을 보낸다.
   ```
   oci ons topic create -c <tenancy> --name udt-alerts
   oci ons subscription create -c <tenancy> --topic-id <topic> --protocol EMAIL --subscription-endpoint <메일>
   # 트래픽 급증: 1시간 송신 10 GB(전국 전체 한 번 분량) 초과
   oci monitoring alarm create … --namespace oci_computeagent \
     --query-text 'NetworksBytesOut[1h]{resourceDisplayName = "udt-gate"}.sum() > 10000000000'
   # VM 멈춤·회수: 30분 넘게 지표 없음
   oci monitoring alarm create … --namespace oci_computeagent \
     --query-text 'CpuUtilization[5m]{resourceDisplayName = "udt-gate"}.absent()' --pending-duration PT30M
   ```

## 운영

| 할 일 | 방법 |
|---|---|
| 기준값 바꾸기 | `server_gate.py`의 상수를 고치고 4번을 다시 실행 |
| 거절 기록 보기 | `ssh -i ~/.ssh/udt-gate.key ubuntu@<IP> journalctl -u udt-gate --since today` |
| 요청 기록 보기 | `/var/log/nginx/udt.log` (시각, IP, 상태, 바이트, 경로, UA, 설치 ID) |
| 비상 차단 (전부 끊기) | `ssh -i ~/.ssh/udt-gate.key ubuntu@<IP> sudo systemctl stop nginx`, 또는 콘솔 → 버킷 → Pre-Authenticated Requests → 삭제 |
| PAR 교체 (만료·유출) | 1·2번으로 새 PAR을 만들고 4번을 다시 실행, 그 다음 옛 PAR을 삭제한다 |
| VM IP가 바뀜 | 6번처럼 `DATA_DOMESTIC_BASE_URL`을 바꾸고 upload를 실행한다 |
| OS 보안 업데이트 | Ubuntu 기본 `unattended-upgrades`가 자동으로 처리한다 |

## 되돌리기 (VM 장애·계정 문제)

사용자는 할 일이 없다. 플러그인은 세션마다 매니페스트를 읽고, 옛 주소가 실패하면 매니페스트를 다시 읽는다. 이미 받은 팩은 사용자 PC에 그대로 남는다.

```
oci os bucket update --profile SESSION --auth security_token --name urbandesigntool-data --public-access-type ObjectReadWithoutList
```

그다음 `constants.DATA_DOMESTIC_BASE_URL = DATA_DOMESTIC_BUCKET_URL`로 되돌리고 `python3 scripts/dev_deploy.py upload`를 실행한다.

## 한계와 확인할 것

- IP와 설치 ID를 함께 바꿔 가며 받는 상대는 막을 수 없다. 무료 구조의 한계로 받아들인다.
- VM이 멈추면 새 팩 다운로드도 멈춘다. 이때는 위 '되돌리기'를 한다.
- 유휴 VM 회수 규정(7일 동안 CPU·네트워크 사용률이 낮으면 회수)이 이 계정에 적용되는지 확인이 필요하다.
- Ubuntu nginx 패키지에 `auth_request` 모듈이 들어 있다고 보고 썼다. `install`이 `nginx -t`를 실행하므로 모듈이 없으면 그 자리에서 멈춘다.
