{{- define "dash.labels" -}}
app.kubernetes.io/part-of: dash
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "dash.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://dash-redis:6379/0
{{- else -}}
{{- required "redis.externalUrl is required when redis.enabled is false" .Values.redis.externalUrl -}}
{{- end -}}
{{- end }}

{{/* Env shared by `dash serve`, `dash worker` and `dash migrate`. */}}
{{- define "dash.env" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.config }}
      key: {{ .Values.secrets.databaseUrlKey }}
- name: REDIS_URL
  value: {{ include "dash.redisUrl" . | quote }}
- name: HERMES_BASE_URL
  value: {{ .Values.hermes.baseUrl | quote }}
- name: HERMES_MODEL
  value: {{ .Values.hermes.model | quote }}
- name: HERMES_API_KEY
  valueFrom:
    secretKeyRef:
      name: dash-hermes
      key: API_SERVER_KEY
- name: EMBED_MODEL
  value: {{ .Values.memory.embedModel | quote }}
- name: EXTRACT_MODEL
  value: {{ .Values.memory.extractModel | quote }}
- name: MEMORY_TOP_K
  value: {{ .Values.memory.topK | quote }}
{{- if .Values.nango.enabled }}
- name: NANGO_URL
  value: http://dash-nango:3003
- name: NANGO_PUBLIC_URL
  value: https://{{ .Values.nango.host }}
- name: NANGO_CONNECT_URL
  value: https://{{ .Values.nango.connectHost }}
- name: NANGO_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: dash
      key: NANGO_SECRET_KEY
      # Only known after Nango's first boot (copied from its dashboard), so
      # dash must start without it and show "Nango is not configured".
      optional: true
{{- end }}
{{- end }}
