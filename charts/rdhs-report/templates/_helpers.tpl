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

{{- define "rdhs-report.syncName" -}}
{{ include "rdhs-report.fullname" . }}-sync
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

{{- define "rdhs-report.ingestToken" -}}
{{- if .Values.secrets.create -}}
{{- required "secrets.web.data.RDHS_INGEST_TOKEN is required when secrets.create=true" .Values.secrets.web.data.RDHS_INGEST_TOKEN -}}
{{- else -}}
{{- required "sync.ingestToken is required when secrets.create=false" .Values.sync.ingestToken -}}
{{- end -}}
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
{{- if lt (int .Values.web.replicaCount) 1 }}
{{- fail "web.replicaCount must be positive" }}
{{- end }}
{{- if ne .Values.database.driver "mysql" }}
{{- fail "database.driver must be mysql for Kubernetes production" }}
{{- end }}
{{- $_ := required "database.mysql.host is required" .Values.database.mysql.host }}
{{- $_ := required "database.mysql.database is required" .Values.database.mysql.database }}
{{- $_ := required "database.mysql.secretName is required" .Values.database.mysql.secretName }}
{{- if .Values.database.mysql.credentials.create }}
{{- $_ := required "database.mysql.credentials.user is required when credentials.create=true" .Values.database.mysql.credentials.user }}
{{- $_ := required "database.mysql.credentials.password is required when credentials.create=true" .Values.database.mysql.credentials.password }}
{{- end }}
{{- if or (lt (int .Values.database.mysql.port) 1) (gt (int .Values.database.mysql.port) 65535) }}
{{- fail "database.mysql.port must be between 1 and 65535" }}
{{- end }}
{{- if lt (int .Values.database.mysql.connectionLimit) 1 }}
{{- fail "database.mysql.connectionLimit must be positive" }}
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
{{- if le (int .Values.sync.currentRefreshTimeoutSeconds) (int .Values.sync.reportCommandTimeoutSeconds) }}
{{- fail "sync.currentRefreshTimeoutSeconds must exceed sync.reportCommandTimeoutSeconds" }}
{{- end }}
{{- if lt (int .Values.sync.cron.activeDeadlineSeconds) (add (mul 2 (int .Values.sync.reportCommandTimeoutSeconds)) 60) }}
{{- fail "sync.cron.activeDeadlineSeconds must allow two report commands plus shutdown time" }}
{{- end }}
{{- if lt (int .Values.sync.outputRetentionMonths) 1 }}
{{- fail "sync.outputRetentionMonths must be positive" }}
{{- end }}
{{- if or (lt (int .Values.sync.leaseTtlSeconds) (int .Values.sync.cron.activeDeadlineSeconds)) (gt (int .Values.sync.leaseTtlSeconds) 3600) }}
{{- fail "sync.leaseTtlSeconds must cover the CronJob deadline and not exceed 3600" }}
{{- end }}
{{- if .Values.secrets.create }}
{{- $_ := required "secrets.web.name is required when secrets.create=true" .Values.secrets.web.name -}}
{{- $_ := required "secrets.web.data.RDHS_INGEST_TOKEN is required when secrets.create=true" .Values.secrets.web.data.RDHS_INGEST_TOKEN -}}
{{- else }}
{{- $_ := required "sync.ingestToken is required when secrets.create=false" .Values.sync.ingestToken -}}
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
{{- if not .Values.networkPolicy.mysqlEgress }}
{{- fail "networkPolicy.mysqlEgress is required when NetworkPolicy is enabled" }}
{{- end }}
{{- end }}
{{- end }}
