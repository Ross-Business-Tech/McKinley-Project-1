McKinley · Phase 1 Customer Service AI Agent

# McKinley AI Agent Flow

Instruction needed (I-xx) Data needed (D-xx) Function module Start Step / decision Outcome Human handoff

I-xx step needs a written rule, script or template: **27** D-xx step needs a data source or list: **14** [See full inputs checklist](#inputs)

## Overall Workflow

Handoff triggers, any step

EmergencyAsks for a personComplaint or upset callerLegal, billing or rent disputeFair Housing sensitiveAI unsure twiceVendor contactUnverified caller asking for private info

## Function Breakdown

[1Phone and Voice Support](#f1)[2SMS and Email](#f2)[3Caller Type Classification](#f3)[4Property and Leasing FAQs](#f4)[5Tour Scheduling](#f5)[6Maintenance Request Intake](#f6)[7Create and Update Maintenance Work Orders](#f7)[8Request Status Lookup](#f8)[9Human Handoff and Escalation](#f9)

### Entry layer

1

#### Phone and Voice Support

Answer or transfer calls, convert speech to text, generate responses, and escalate to a human when needed.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-01 | Instruction | Call greeting script and AI disclosure wording | Team drafts, McKinley approves |
| I-02 | Instruction | When a call must be transferred (asks for a person, emergency, misheard twice) | Team drafts, McKinley approves |
| I-03 | Instruction | Voice reply style: short sentences, read back names, units and numbers | Team drafts |
| I-04 | Instruction | End-of-call summary and SMS confirmation template | Team drafts, McKinley approves |
| I-05 | Instruction | Response-time promises for callbacks and follow-ups | McKinley |
| D-01 | Data | Office hours for each property | McKinley |
| D-02 | Data | Staff transfer numbers by team | McKinley (sample data for prototype) |
| D-03 | Data | On-call schedule and contacts | McKinley (sample data for prototype) |

2

#### SMS and Email

Receive inquiries, answer common questions, organize messages, and preserve conversation context.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-06 | Instruction | SMS opt-out keywords and consent wording | McKinley (compliance) |
| I-07 | Instruction | Tone, length and signature rules for SMS and email | Team drafts, McKinley approves |
| I-08 | Instruction | Topic and status tags used to organize conversations | Team drafts |
| D-04 | Data | Contact records: phone numbers and emails | Yardi (sample data for prototype) |

3

#### Caller Type Classification

Identify prospective renters, current residents, vendors, or other contacts, then apply the appropriate workflow and data permissions.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-09 | Instruction | Question that asks who the contact is | Team drafts |
| I-10 | Instruction | Resident verification rules: which details to match, number of tries | McKinley |
| I-11 | Instruction | Permission matrix: what each caller type may see and do | McKinley |
| D-05 | Data | Resident and unit records | Yardi (sample data for prototype) |
| D-06 | Data | Vendor list | Yardi (sample data for prototype) |

### Service workflows

4

#### Property and Leasing FAQs

Answer questions about rent, floor plans, availability, amenities, parking, pet policies, and community rules using approved information.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-05 | Instruction | Response-time promises for callbacks and follow-ups | McKinley |
| I-12 | Instruction | FAQ topic list | Team drafts |
| I-13 | Instruction | Fair Housing topics to avoid and the approved response | McKinley (legal) |
| I-14 | Instruction | Answer rules: approved information only, no promises on price or offers | Team drafts, McKinley approves |
| D-07 | Data | Approved knowledge base per property: rent, floor plans, amenities, parking, pets, rules | McKinley documents |
| D-08 | Data | Live unit availability and pricing | Yardi (sample data for prototype) |

5

#### Tour Scheduling

Collect tour preferences, check available time slots, and create or submit tour requests.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-15 | Instruction | Required tour questions and tour types offered | McKinley leasing team |
| I-16 | Instruction | Tour confirmation and reminder templates | Team drafts |
| D-08 | Data | Live unit availability and pricing | Yardi (sample data for prototype) |
| D-09 | Data | Tour calendar and agent availability | McKinley (sample data for prototype) |
| D-10 | Data | Lead record fields | Yardi CRM (sample data for prototype) |

6

#### Maintenance Request Intake

Collect issue location, description, urgency, and access availability to create a structured maintenance request.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-17 | Instruction | Emergency definition list | McKinley maintenance |
| I-18 | Instruction | Safety instructions for each emergency type | McKinley maintenance |
| I-19 | Instruction | Maintenance categories and required intake fields | McKinley maintenance |
| I-20 | Instruction | Approved self-troubleshooting guides (e.g., reset breaker) | McKinley maintenance |
| D-03 | Data | On-call schedule and contacts | McKinley (sample data for prototype) |

7

#### Create and Update Maintenance Work Orders

Write confirmed maintenance details into the work-order system, or route them to an employee for approval before creation.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-21 | Instruction | Approval rules: which requests need staff sign-off | McKinley |
| I-22 | Instruction | Work order notification templates (created, rejected, updated, completed) | Team drafts |
| I-23 | Instruction | Target timing by priority and overdue threshold | McKinley maintenance |
| I-24 | Instruction | What residents may change or cancel at each work order status | McKinley maintenance |
| D-11 | Data | Work order system and fields | Yardi (mock system for prototype) |
| D-12 | Data | Approver list | McKinley |

8

#### Request Status Lookup

Allow residents to check maintenance progress and receive notifications when the status changes.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-22 | Instruction | Work order notification templates (created, rejected, updated, completed) | Team drafts |
| I-23 | Instruction | Target timing by priority and overdue threshold | McKinley maintenance |
| D-11 | Data | Work order system and fields | Yardi (mock system for prototype) |
| D-13 | Data | Resident contact preferences | Yardi (sample data for prototype) |

### Safety net

9

#### Human Handoff and Escalation

Transfer uncertain, sensitive, complaint-related, or high-risk issues to the appropriate employee with a summary and conversation history.

Inputs needed in this flow

| Code | Type | What the team needs to prepare | Suggested source |
| --- | --- | --- | --- |
| I-05 | Instruction | Response-time promises for callbacks and follow-ups | McKinley |
| I-25 | Instruction | Handoff trigger list | Team drafts, McKinley approves |
| I-26 | Instruction | Routing table: issue type to team | McKinley |
| I-27 | Instruction | Handoff summary format | Team drafts, staff review |
| D-01 | Data | Office hours for each property | McKinley |
| D-02 | Data | Staff transfer numbers by team | McKinley (sample data for prototype) |
| D-03 | Data | On-call schedule and contacts | McKinley (sample data for prototype) |
| D-14 | Data | Staff task queue | Team builds for prototype |

## Inputs Checklist

| Code | Type | What the team needs to prepare | Suggested source | Used in |
| --- | --- | --- | --- | --- |
| I-01 | Instruction | Call greeting script and AI disclosure wording | Team drafts, McKinley approves | [1](#f1) |
| I-02 | Instruction | When a call must be transferred (asks for a person, emergency, misheard twice) | Team drafts, McKinley approves | [1](#f1) |
| I-03 | Instruction | Voice reply style: short sentences, read back names, units and numbers | Team drafts | [1](#f1) |
| I-04 | Instruction | End-of-call summary and SMS confirmation template | Team drafts, McKinley approves | [1](#f1) |
| I-05 | Instruction | Response-time promises for callbacks and follow-ups | McKinley | [1](#f1) [4](#f4) [9](#f9) |
| I-06 | Instruction | SMS opt-out keywords and consent wording | McKinley (compliance) | [2](#f2) |
| I-07 | Instruction | Tone, length and signature rules for SMS and email | Team drafts, McKinley approves | [2](#f2) |
| I-08 | Instruction | Topic and status tags used to organize conversations | Team drafts | [2](#f2) |
| I-09 | Instruction | Question that asks who the contact is | Team drafts | [3](#f3) |
| I-10 | Instruction | Resident verification rules: which details to match, number of tries | McKinley | [3](#f3) |
| I-11 | Instruction | Permission matrix: what each caller type may see and do | McKinley | [3](#f3) |
| I-12 | Instruction | FAQ topic list | Team drafts | [4](#f4) |
| I-13 | Instruction | Fair Housing topics to avoid and the approved response | McKinley (legal) | [4](#f4) |
| I-14 | Instruction | Answer rules: approved information only, no promises on price or offers | Team drafts, McKinley approves | [4](#f4) |
| I-15 | Instruction | Required tour questions and tour types offered | McKinley leasing team | [5](#f5) |
| I-16 | Instruction | Tour confirmation and reminder templates | Team drafts | [5](#f5) |
| I-17 | Instruction | Emergency definition list | McKinley maintenance | [6](#f6) |
| I-18 | Instruction | Safety instructions for each emergency type | McKinley maintenance | [6](#f6) |
| I-19 | Instruction | Maintenance categories and required intake fields | McKinley maintenance | [6](#f6) |
| I-20 | Instruction | Approved self-troubleshooting guides (e.g., reset breaker) | McKinley maintenance | [6](#f6) |
| I-21 | Instruction | Approval rules: which requests need staff sign-off | McKinley | [7](#f7) |
| I-22 | Instruction | Work order notification templates (created, rejected, updated, completed) | Team drafts | [7](#f7) [8](#f8) |
| I-23 | Instruction | Target timing by priority and overdue threshold | McKinley maintenance | [7](#f7) [8](#f8) |
| I-24 | Instruction | What residents may change or cancel at each work order status | McKinley maintenance | [7](#f7) |
| I-25 | Instruction | Handoff trigger list | Team drafts, McKinley approves | [9](#f9) |
| I-26 | Instruction | Routing table: issue type to team | McKinley | [9](#f9) |
| I-27 | Instruction | Handoff summary format | Team drafts, staff review | [9](#f9) |
| D-01 | Data | Office hours for each property | McKinley | [1](#f1) [9](#f9) |
| D-02 | Data | Staff transfer numbers by team | McKinley (sample data for prototype) | [1](#f1) [9](#f9) |
| D-03 | Data | On-call schedule and contacts | McKinley (sample data for prototype) | [1](#f1) [6](#f6) [9](#f9) |
| D-04 | Data | Contact records: phone numbers and emails | Yardi (sample data for prototype) | [2](#f2) |
| D-05 | Data | Resident and unit records | Yardi (sample data for prototype) | [3](#f3) |
| D-06 | Data | Vendor list | Yardi (sample data for prototype) | [3](#f3) |
| D-07 | Data | Approved knowledge base per property: rent, floor plans, amenities, parking, pets, rules | McKinley documents | [4](#f4) |
| D-08 | Data | Live unit availability and pricing | Yardi (sample data for prototype) | [4](#f4) [5](#f5) |
| D-09 | Data | Tour calendar and agent availability | McKinley (sample data for prototype) | [5](#f5) |
| D-10 | Data | Lead record fields | Yardi CRM (sample data for prototype) | [5](#f5) |
| D-11 | Data | Work order system and fields | Yardi (mock system for prototype) | [7](#f7) [8](#f8) |
| D-12 | Data | Approver list | McKinley | [7](#f7) |
| D-13 | Data | Resident contact preferences | Yardi (sample data for prototype) | [8](#f8) |
| D-14 | Data | Staff task queue | Team builds for prototype | [9](#f9) |