from __future__ import annotations

import uuid


def build_qwc_xml(
    *,
    app_name: str,
    app_url: str,
    app_support_url: str,
    username: str,
    owner_id: str,
    file_id: str,
    app_id: str | None = None,
    run_every_n_minutes: int = 15,
) -> str:
    app_id = app_id or str(uuid.uuid4())
    return f"""<?xml version="1.0"?>
<QBWCXML>
  <AppName>{app_name}</AppName>
  <AppID>{app_id}</AppID>
  <AppURL>{app_url}</AppURL>
  <AppDescription>HiveFlow QuickBooks Desktop sync</AppDescription>
  <AppSupport>{app_support_url}</AppSupport>
  <UserName>{username}</UserName>
  <OwnerID>{owner_id}</OwnerID>
  <FileID>{file_id}</FileID>
  <QBType>QBFS</QBType>
  <Scheduler>
    <RunEveryNMinutes>{run_every_n_minutes}</RunEveryNMinutes>
  </Scheduler>
  <IsReadOnly>false</IsReadOnly>
</QBWCXML>
"""
