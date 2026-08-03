# Gold Price History Data

금시세 위젯 앱을 위한 금시세 히스토리 데이터 저장소입니다.

- `history.json`: 공식 KRX 1kg 종가 이력입니다. 같은 날짜의 LBMA·USD/KRW 자료가 모두 있을 때만 프리미엄을 제공하며, 비교 시장 휴장일에는 관련 필드가 `null`이고 `premiumAvailable`이 `false`입니다.
- `realtime.json`: 최근 KRX 종가와 조회 시점의 국제 금·환율 참고값입니다. 각 기준일이 다르므로 현재 프리미엄은 `null`로 제공합니다.

검증은 다음 명령으로 실행합니다.

```bash
python -m unittest discover -s tests
```
