# Payload Directory Application Bootstrap

Status: initialization plan only

This document defines the empty, deployable application template for the proposed
GeoDirectory-to-Payload product. It complements `GDirectory_replatforming.md` but does not
define migration, directory, search, map, account, review, payment, or parity logic. All
runtime dependencies must be pinned by the generated lockfile and compatibility-tested
before the template is accepted.

## 1. Local development setup

Bootstrap a TypeScript pnpm workspace with two deployable applications: Payload with
Next.js for the CMS Admin and API, and Astro for the public website. Next.js is an
implementation detail of Payload and must not become the public rendering layer. The two
applications share versioned generated types and configuration contracts, not a runtime.

### Toolchain and application skeleton

- Pin Node.js 24 LTS in `.node-version` and the repository `engines` field.
- Use pnpm through Corepack and commit `pnpm-lock.yaml`.
- Create `apps/cms` from Payload's blank template, then pin a compatibility-tested Payload
  3 and Next.js 16 pair. Use strict TypeScript, the Next.js App Router, and Turbopack only
  within this application.
- Wrap the CMS `next.config` with `withPayload` and set `output: 'standalone'` so its build
  runs locally or in either AWS container profile.
- Keep Payload Admin and API routes under `apps/cms/src/app/(payload)`. Add only an
  auth-enabled `Users` collection and a `Media` upload collection; do not add directory
  collections or behavior.
- Create `apps/web` from Astro's minimal TypeScript template. Configure the Astro Node
  adapter so the same application can prerender suitable routes and serve dynamic routes
  from a long-running Node container.
- Use Astro's built-in Vite pipeline rather than configuring Vite independently. Enable
  React through `@astrojs/react` as the only island framework for future interactive
  components; do not create directory, search, map, account, or review components yet.
- Generate Payload's TypeScript definitions into a small workspace package consumed by
  the Astro application. Generated types may cross the boundary, but the public frontend
  must access content through Payload's supported API rather than importing CMS runtime
  modules or querying PostgreSQL directly.

### Local service boundary

Provide `compose.yaml` for disposable development dependencies while running both
applications on the host for fast refresh:

- PostgreSQL 16 with PostGIS enabled, matching production and preserving a future RDS
  migration path;
- MinIO as an S3-compatible media backend;
- Mailpit as a local SMTP sink compatible with the future SES/Nodemailer boundary.

Configure Payload with `@payloadcms/db-postgres`, `@payloadcms/storage-s3`, and the
Nodemailer email adapter from environment variables. Local and AWS deployments must use
the same application adapters; only endpoints, credentials, and resource names change.
MinIO and Mailpit are local-only, disposable substitutes: production uses S3 and SES.
Commit `.env.example`, never secrets, with at least the database URL, Payload secret, CMS
and public URLs, S3 endpoint/region/bucket settings, SMTP settings, and the public
frontend's CMS API origin.

Do not make LocalStack a default dependency. Its maintained distribution introduces an
account, token, and commercial licensing boundary without improving this template's two
simple integrations. Reconsider an optional LocalStack profile only if the application
later depends on several additional AWS services such as SQS, SNS, EventBridge, or Lambda.
Do not add AWS SAM CLI either: these deployment profiles run long-lived containers, not
Lambda functions.

### Repository and lifecycle files

The empty application repository should include:

```text
payload-directory/
├── apps/
│   ├── cms/
│   │   ├── next.config.ts
│   │   ├── payload.config.ts
│   │   ├── src/app/(payload)/
│   │   ├── src/collections/Users.ts
│   │   ├── src/collections/Media.ts
│   │   └── src/migrations/
│   └── web/
│       ├── astro.config.ts
│       └── src/pages/
├── packages/
│   └── payload-types/          # generated CMS types only
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── .node-version
├── Dockerfile.cms
├── Dockerfile.web
├── compose.yaml
├── .env.example
└── infra/                       # reserved for the CDK application
```

Add root scripts for concurrent development, per-application production builds and starts,
linting, type checking, Payload type generation, migration generation/application, and
production-like smoke tests for both containers. Generate and commit the initial database
migration; production must apply migrations explicitly instead of relying on
development-time schema synchronization.

Keep the fast local test loop independent of an AWS account. Run application unit and
integration tests against PostgreSQL/PostGIS, MinIO, and Mailpit. Run CDK synthesis and CDK
unit/assertion tests locally, but do not treat local service emulation as proof of AWS
compatibility. A disposable AWS development environment must later verify real S3 uploads,
SES delivery, IAM permissions, secrets, DNS/TLS, image deployment, backup, and restoration
before either production profile is accepted.

Local bootstrap is complete when a clean clone can install from the lockfile, start the
compose services, start both applications, apply migrations, create the first
administrator, upload media through the S3 adapter, inspect a captured Mailpit message,
open Payload Admin and the Astro site, and produce and run both production images. This
gate verifies the template only, not directory functionality or real AWS integration.

## 2. AWS CDK and deployment-compatible infrastructure

Reserve `infra/` for an AWS CDK v2 application written in TypeScript and managed by the
same pinned Node/pnpm toolchain. The CDK application will offer two single-server deployment
profiles. Both profiles run the same production images and intentionally match the current
site's simple operational model instead of introducing Fargate, an Application Load
Balancer, a NAT Gateway, RDS, or RDS Proxy at bootstrap time.

### Shared deployment boundaries

- Build immutable, multi-stage, multi-platform CMS and web images from the Next.js
  standalone and Astro Node outputs. Publish AMD64 and ARM64 variants of each under stable
  image manifests, and supply all environment-specific configuration at runtime.
- Run the Payload CMS, Astro web application, and PostgreSQL 16 with PostGIS as separate
  containers. Keep database data on encrypted persistent block storage and keep media in a
  private, versioned S3 bucket through Payload's S3 adapter.
- Define separate commands from the CMS image for the API/Admin process, database
  migrations, and the future Payload job worker. The first deployment may run Payload jobs
  in the CMS process.
- Run migrations explicitly before starting a schema-dependent application revision. A
  failed migration must leave the previous application revision running.
- Put a lightweight reverse proxy such as Caddy in front of both applications for HTTPS,
  routing, request limits, compression, and health checks. CloudFront remains optional and
  can be added without changing either application image.
- Use Route 53 for DNS, SES for application email, S3 for media and off-machine database
  backups, and CloudWatch for essential logs, metrics, alarms, and retention.
- Provide an unauthenticated readiness endpoint that exposes no configuration or private
  data. Treat container filesystems and in-memory caches as disposable.
- Parameterize the region, domain, server size, disk size, backup retention, deletion
  protection, and deployment profile. Do not hard-code resource identifiers or secrets.
- Document and test database backup restoration before production acceptance. These
  single-server profiles do not claim high availability; managed RDS and a multi-node
  application tier are later scaling options, not bootstrap requirements.

### Option A: Amazon Lightsail

Make Lightsail the default and least expensive deployment profile:

- Target the general-purpose **4 GB plan at $24/month** for the initial production sizing.
  Allow the **8 GB plan at $44/month** as a configuration-only upgrade if migration tests,
  database size, or measured peaks require more memory.
- Provision one Linux instance, its included static IP and firewall, and an attached
  encrypted block-storage disk dedicated to PostgreSQL data. Keep the operating system and
  replaceable containers on the instance disk.
- Run the CMS, Astro site, PostgreSQL/PostGIS, and reverse-proxy containers with a
  production Compose definition derived from the locally tested services.
- Permit public inbound traffic only on HTTP/HTTPS. Keep administrative access restricted
  to approved source addresses and prefer an auditable remote-management channel over a
  permanently open SSH port.
- Store deployable image references and runtime secrets outside the repository. The later
  CD workflow may provision over the remote-management channel, but it must deploy the same
  immutable images tested locally and retain the previous tags for rollback.
- Schedule encrypted PostgreSQL backups to S3 and retain Lightsail snapshots according to
  the environment policy. A replacement instance must be reconstructible from CDK plus a
  documented database restore.

The expected base infrastructure budget is the $24 or $44 instance plan plus modest block
storage, S3 backup/media, DNS, and logging charges. Exact euro billing depends on exchange
rate and tax treatment.

### Option B: ECS on one EC2 instance

Provide a second profile for teams that want ECS deployment semantics without the fixed
cost of Fargate, an ALB, or managed NAT:

- Create one ECS cluster backed by one Graviton EC2 instance. Start with a 2-vCPU/4-GB
  burstable instance and make an 8-GB size the configuration-only upgrade path.
- Attach an encrypted EBS data volume for PostgreSQL and a single Elastic IP for stable
  ingress. Place the instance in a public subnet with an Internet Gateway; do not create a
  NAT Gateway.
- Register the instance with ECS and run separate CMS, Astro, and PostgreSQL/PostGIS task
  definitions, plus a reverse-proxy sidecar or task. Pin the database task to the host and
  mount only its dedicated persistent volume.
- Use an EC2 instance role for narrowly scoped ECR image pulls, S3 media/backups, runtime
  secret retrieval, and CloudWatch publishing. Containers must not contain long-lived AWS
  credentials.
- Deploy database migrations as an explicit one-off ECS task from the CMS image, then
  update the CMS and Astro services only after migration success. Keep their prior task
  definitions available for application rollback.
- Configure Route 53 to the Elastic IP and terminate TLS at the reverse proxy. CloudFront
  may later sit in front of the origin without adding an ALB.
- Keep desired capacity at exactly one. Replacing the EC2 host is an explicit recovery
  operation that reattaches or restores the database volume and reassociates the Elastic
  IP; automatic horizontal scaling is out of scope for this profile.

The infrastructure bootstrap is complete when CDK can create either profile, deploy the
same locally verified images, apply migrations, start the CMS, Astro, and database
containers, serve HTTPS, persist media and database state, emit useful operational signals,
and prove backup restoration. No GeoDirectory-specific AWS service or application behavior
belongs in this template phase.
