{{- define "rdhs-report.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "rdhs-report.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "rdhs-report.labels" -}}
app.kubernetes.io/name: {{ include "rdhs-report.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end }}

{{- define "rdhs-report.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rdhs-report.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "rdhs-report.webName" -}}
{{ include "rdhs-report.fullname" . }}-web
{{- end }}

{{- define "rdhs-report.runnerName" -}}
{{ include "rdhs-report.fullname" . }}-refresh
{{- end }}

{{- define "rdhs-report.syncName" -}}
{{ include "rdhs-report.fullname" . }}-sync
{{- end }}

{{- define "rdhs-report.sqliteClaimName" -}}
{{- default (include "rdhs-report.fullname" .) .Values.persistence.existingClaim }}
{{- end }}

{{- define "rdhs-report.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "rdhs-report.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- required "serviceAccount.name is required when serviceAccount.create=false" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "rdhs-report.siteUrl" -}}
{{- printf "http://%s:3000%s" (include "rdhs-report.webName" .) .Values.ingress.pathPrefix -}}
{{- end }}

{{- define "rdhs-report.image" -}}
{{- $image := . -}}
{{- $repository := required "image.repository is required" $image.repository -}}
{{- $tag := required "image.tag is required and must be immutable" $image.tag -}}
{{- if eq $tag "latest" }}
{{- fail "image.tag must not use the mutable latest tag" }}
{{- end }}
{{- printf "%s:%s" $repository $tag -}}
{{- end }}

{{- define "rdhs-report.validate" -}}
{{- if ne (int .Values.web.replicaCount) 1 }}
{{- fail "web.replicaCount must be 1 because the SQLite PVC has one writer" }}
{{- end }}
{{- if ne .Values.strategy.type "Recreate" }}
{{- fail "strategy.type must be Recreate because the SQLite PVC is ReadWriteOnce" }}
{{- end }}
{{- if not .Values.persistence.enabled }}
{{- fail "persistence.enabled must be true for the SQLite database" }}
{{- end }}
{{- if not (deepEqual .Values.persistence.accessModes (list "ReadWriteOnce")) }}
{{- fail "persistence.accessModes must be exactly [ReadWriteOnce]" }}
{{- end }}
{{- if ne (int .Values.sync.replicaCount) 1 }}
{{- fail "sync.replicaCount must be 1 because the refresh Runner has no distributed lock" }}
{{- end }}
{{- if ne .Values.sync.cron.schedule "0 9 1 * *" }}
{{- fail "sync.cron.schedule must be 0 9 1 * *" }}
{{- end }}
{{- if ne .Values.sync.cron.timeZone "Asia/Shanghai" }}
{{- fail "sync.cron.timeZone must be Asia/Shanghai" }}
{{- end }}
{{- if lt (int .Values.sync.reportCommandTimeoutSeconds) 1 }}
{{- fail "sync.reportCommandTimeoutSeconds must be positive" }}
{{- end }}
{{- if le (int .Values.sync.runner.timeoutSeconds) (int .Values.sync.reportCommandTimeoutSeconds) }}
{{- fail "sync.runner.timeoutSeconds must exceed sync.reportCommandTimeoutSeconds" }}
{{- end }}
{{- if lt (int .Values.sync.cron.activeDeadlineSeconds) (add (mul 2 (int .Values.sync.reportCommandTimeoutSeconds)) 60) }}
{{- fail "sync.cron.activeDeadlineSeconds must allow two report commands plus shutdown time" }}
{{- end }}
{{- if lt (int .Values.sync.outputRetentionMonths) 1 }}
{{- fail "sync.outputRetentionMonths must be positive" }}
{{- end }}
{{- $_ := required "syncStorage.nfs.server is required for the shared Runner/CronJob output" .Values.syncStorage.nfs.server }}
{{- $_ := required "syncStorage.nfs.path is required for the shared Runner/CronJob output" .Values.syncStorage.nfs.path }}
{{- $_ := required "secrets.web.name is required" .Values.secrets.web.name -}}
{{- if .Values.secrets.create }}
{{- $_ := required "secrets.web.data.RDHS_INGEST_TOKEN is required when secrets.create=true" .Values.secrets.web.data.RDHS_INGEST_TOKEN -}}
{{- $_ := required "secrets.web.data.RDHS_REFRESH_WEBHOOK_TOKEN is required when secrets.create=true" .Values.secrets.web.data.RDHS_REFRESH_WEBHOOK_TOKEN -}}
{{- end }}
{{- $pathPrefix := required "ingress.pathPrefix is required" .Values.ingress.pathPrefix }}
{{- if not (hasPrefix "/" $pathPrefix) }}
{{- fail "ingress.pathPrefix must start with /" }}
{{- end }}
{{- if hasSuffix "/" $pathPrefix }}
{{- fail "ingress.pathPrefix must not end with /" }}
{{- end }}
{{- if .Values.networkPolicy.enabled }}
{{- if not .Values.networkPolicy.ingressController.namespaceSelector }}
{{- fail "networkPolicy.ingressController.namespaceSelector is required when NetworkPolicy is enabled" }}
{{- end }}
{{- if not .Values.networkPolicy.ingressController.podSelector }}
{{- fail "networkPolicy.ingressController.podSelector is required when NetworkPolicy is enabled" }}
{{- end }}
{{- if not .Values.networkPolicy.meegleEgress }}
{{- fail "networkPolicy.meegleEgress is required when NetworkPolicy is enabled" }}
{{- end }}
{{- end }}
{{- end }}
