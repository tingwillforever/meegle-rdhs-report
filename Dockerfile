ARG RDHS_BASE_IMAGE=artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report-base:node22-python3-meegle-cli-1.1.5
ARG RDHS_BASE_PATH=/meegle-rdhs-report

FROM ${RDHS_BASE_IMAGE} AS builder

ARG RDHS_BASE_PATH
WORKDIR /app
ENV DEPLOY_TARGET=k8s \
    RDHS_BASE_PATH=${RDHS_BASE_PATH}
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build:k8s

FROM ${RDHS_BASE_IMAGE}

ARG RDHS_BASE_PATH

WORKDIR /app
ENV HOME=/home/node \
    NODE_ENV=production \
    DEPLOY_TARGET=k8s \
    RDHS_BASE_PATH=${RDHS_BASE_PATH} \
    RDHS_STORAGE=mysql \
    RDHS_WORKSPACE_ROOT=/opt/rdhs-workspace \
    RDHS_PYTHON_BIN=python3 \
    RDHS_OUTPUT_ROOT=/var/lib/rdhs-sync \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY --from=builder /app/dist ./dist
COPY scripts ./scripts

COPY vendor/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py /opt/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_analysis.py /opt/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_analysis.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_data.py /opt/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_data.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_models.py /opt/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_models.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_renderer.py /opt/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_renderer.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_runtime.py /opt/rdhs-workspace/topics/rdhs-operations/impl/periodic_report_runtime.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/impl/product_improvement_enrichment.py /opt/rdhs-workspace/topics/rdhs-operations/impl/product_improvement_enrichment.py
COPY vendor/rdhs-workspace/topics/rdhs-operations/config/periodic_report.yaml /opt/rdhs-workspace/topics/rdhs-operations/config/periodic_report.yaml
COPY vendor/rdhs-workspace/topics/rdhs-operations/config/initial_super_team_mappings.csv /opt/rdhs-workspace/topics/rdhs-operations/config/initial_super_team_mappings.csv

RUN mkdir -p /home/node /var/lib/rdhs-sync \
  && chown -R node:node /app /home/node /var/lib/rdhs-sync /opt/rdhs-workspace
USER node

EXPOSE 3000 8765
CMD ["npm", "run", "start:k8s"]
