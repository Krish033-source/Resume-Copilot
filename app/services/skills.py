"""Skill taxonomy, alias handling and role profiles.

One shared vocabulary is used for resumes, job descriptions and papers so that
scores are consistent everywhere.
"""
import re
from collections import Counter

_RAW = """
lang | python | py, python3
lang | java |
lang | javascript | js, es6, ecmascript, vanilla js
lang | typescript | ts
lang | c++ | cpp, c/c++
lang | c | c language, c programming
lang | c# | csharp, c sharp
lang | go | golang
lang | rust |
lang | kotlin |
lang | swift |
lang | php |
lang | ruby |
lang | scala |
lang | r | r programming, rstudio
lang | matlab |
lang | dart |
lang | sql | t-sql, pl/sql, plsql
lang | bash | shell scripting, shell script, shell
lang | html | html5
lang | css | css3
frontend | react | react.js, reactjs
frontend | next.js | nextjs, next js
frontend | vue | vue.js, vuejs
frontend | angular | angularjs, angular.js
frontend | svelte |
frontend | tailwind css | tailwind, tailwindcss
frontend | redux | redux toolkit
frontend | bootstrap |
frontend | webpack |
frontend | vite |
frontend | jquery |
frontend | sass | scss
frontend | responsive design | responsive web design
backend | node.js | nodejs, node js, node
backend | express | express.js, expressjs
backend | django | drf, django rest framework
backend | flask |
backend | fastapi |
backend | spring boot | springboot, spring framework, spring
backend | .net | dotnet, .net core, asp.net, asp.net core
backend | laravel |
backend | graphql |
backend | rest api | rest apis, restful, restful api, restful apis, rest
backend | grpc |
backend | microservices | micro-services, microservice
backend | websockets | websocket, socket.io
backend | jwt | json web token, oauth, oauth2
data | postgresql | postgres, psql
data | mysql | mariadb
data | mongodb | mongo
data | redis |
data | sqlite |
data | elasticsearch | elastic search, opensearch
data | cassandra |
data | dynamodb |
data | firebase | firestore
data | supabase |
data | nosql | no-sql
data | database design | schema design, normalization, data modeling, data modelling
cloud | aws | amazon web services, ec2, s3, aws lambda
cloud | azure | microsoft azure
cloud | gcp | google cloud, google cloud platform
cloud | docker | dockerfile, docker compose, containerization
cloud | kubernetes | k8s
cloud | terraform | infrastructure as code, iac
cloud | ansible |
cloud | jenkins |
cloud | github actions | gitlab ci
cloud | ci/cd | cicd, ci cd, continuous integration, continuous deployment
cloud | linux | ubuntu, unix
cloud | nginx |
cloud | git | version control
cloud | github |
cloud | prometheus |
cloud | grafana |
cloud | helm |
cloud | serverless |
ml | machine learning | ml
ml | deep learning | neural networks, neural network, cnn, rnn, lstm
ml | nlp | natural language processing
ml | computer vision | cv, image processing
ml | llm | llms, large language models, large language model
ml | langchain | langgraph, llamaindex
ml | hugging face | huggingface, transformers
ml | rag | retrieval augmented generation, retrieval-augmented generation
ml | generative ai | genai, gen ai, generative models
ml | prompt engineering | prompt design
ml | vector database | vector databases, pinecone, faiss, chromadb, weaviate, pgvector
ml | pandas |
ml | numpy |
ml | scikit-learn | sklearn, scikit learn
ml | tensorflow |
ml | pytorch | torch
ml | keras |
ml | opencv |
ml | xgboost | lightgbm, gradient boosting
ml | reinforcement learning |
ml | time series | forecasting
ml | feature engineering |
ml | mlops | model deployment, model serving
ml | mlflow | weights & biases, wandb
ml | statistics | statistical analysis, hypothesis testing, a/b testing
ml | data analysis | data analytics, exploratory data analysis, eda
ml | data visualization | data visualisation, matplotlib, seaborn, plotly
ml | jupyter | jupyter notebook, google colab, colab
bi | tableau |
bi | power bi | powerbi
bi | excel | advanced excel, ms excel, microsoft excel, vlookup, pivot tables
bi | looker | looker studio, data studio
dataeng | apache spark | spark, pyspark
dataeng | hadoop | hive, hdfs
dataeng | kafka | apache kafka
dataeng | airflow | apache airflow
dataeng | etl | elt, data pipeline, data pipelines
dataeng | data warehousing | data warehouse
dataeng | snowflake |
dataeng | bigquery |
dataeng | dbt |
mobile | android | android studio
mobile | ios | xcode
mobile | flutter |
mobile | react native |
mobile | jetpack compose |
mobile | swiftui |
security | cybersecurity | cyber security, infosec, information security
security | penetration testing | pentesting, pen testing, ethical hacking, red team
security | owasp | owasp top 10
security | burp suite | burpsuite
security | wireshark |
security | nmap |
security | metasploit |
security | siem | splunk, qradar, sentinel
security | incident response | threat hunting, threat detection
security | network security | firewall, firewalls, ids/ips, vpn
security | cryptography | encryption
security | vulnerability assessment | vapt, vulnerability scanning, nessus
security | kali linux |
security | soc | security operations
testing | selenium |
testing | cypress |
testing | playwright |
testing | jest |
testing | pytest | unittest
testing | junit | testng
testing | postman |
testing | test automation | automation testing, automated testing
testing | unit testing | integration testing
testing | manual testing | test cases, test case design
testing | bug tracking | defect tracking
design | figma |
design | ui/ux | ui ux, ux design, ui design, user experience, user interface
design | wireframing | wireframes, wireframe
design | prototyping | prototype, prototypes
design | adobe xd |
design | photoshop | adobe photoshop
design | user research | usability testing, user testing
design | design systems | design system
cs | data structures | dsa, data structures and algorithms, algorithms, data structure
cs | oop | object oriented programming, object-oriented programming, object oriented
cs | system design | low level design, high level design, lld, hld, scalable systems
cs | design patterns |
cs | operating systems | os concepts
cs | computer networks | tcp/ip, osi model, computer networking
cs | dbms | database management systems
cs | multithreading | concurrency, concurrent programming, parallel programming
cs | agile | scrum, kanban
cs | jira |
cs | tdd | test driven development, test-driven development
cs | code review | code reviews
chain | blockchain |
chain | solidity |
chain | web3 | web3.js, ethers.js
chain | ethereum |
chain | smart contracts | smart contract
research | research | literature review, research paper, research papers
research | academic writing | latex, technical writing
research | publications | published, publication, peer-reviewed, peer reviewed
"""

# canonical -> (category, [aliases])
SKILLS: dict[str, tuple[str, list[str]]] = {}
for _line in _RAW.strip().splitlines():
    _cat, _name, _al = [p.strip() for p in _line.split("|")]
    SKILLS[_name] = (_cat, [a.strip() for a in _al.split(",") if a.strip()])

CATEGORY_LABELS = {
    "lang": "Languages", "frontend": "Frontend", "backend": "Backend", "data": "Databases",
    "cloud": "Cloud & DevOps", "ml": "ML & AI", "bi": "BI & Analytics", "dataeng": "Data Engineering",
    "mobile": "Mobile", "security": "Security", "testing": "Testing", "design": "Design",
    "cs": "CS Fundamentals", "chain": "Blockchain", "research": "Research",
}

# Tokens that collide with ordinary English: only accepted in list-like lines, case-sensitive.
AMBIGUOUS = {"go", "r", "c", "rest", "node", "shell", "spring", "transformers", "research",
             "published", "publication", "sentinel", "soc", "cv", "torch", "ml", "os concepts",
             "prototype", "prototypes", "py", "ts", "js"}
CASE_SENSITIVE_CANON = {"go": "Go", "r": "R", "c": "C"}


def _compile():
    table = []  # (regex, canonical, ambiguous)
    for canon, (_cat, aliases) in SKILLS.items():
        for term in [canon] + aliases:
            amb = (term in AMBIGUOUS) or (canon in CASE_SENSITIVE_CANON and term == canon)
            esc = re.escape(term)
            flags = 0 if amb else re.IGNORECASE
            if amb and canon in CASE_SENSITIVE_CANON and term == canon:
                esc = re.escape(CASE_SENSITIVE_CANON[canon])
            elif amb:
                flags = re.IGNORECASE
            pat = re.compile(r"(?<![\w+#.])" + esc + r"(?![\w+#]|\.\w)", flags)
            table.append((pat, canon, amb))
    return table


_TABLE = _compile()
_BULLET_RE = re.compile(r"^[\s\u2022\u25aa\u25cf\u25e6\uf0b7\u2023\u2043\u2219\-–—*·▪●•]+")


def _is_listlike(line: str) -> bool:
    return len(re.findall(r"[,|/•·;]", line)) >= 2 or ":" in line and "," in line


def extract_skills(text: str) -> Counter:
    """Return Counter(canonical_skill -> mentions). Overlapping alias hits count once."""
    found: Counter = Counter()
    for line in text.splitlines():
        if not line.strip():
            continue
        listlike = _is_listlike(line)
        spans: dict[str, list[tuple[int, int]]] = {}
        for pat, canon, amb in _TABLE:
            if amb and not listlike:
                continue
            for m in pat.finditer(line):
                spans.setdefault(canon, []).append(m.span())
        for canon, sp in spans.items():
            sp.sort(key=lambda x: (x[0], -(x[1] - x[0])))
            kept, end = 0, -1
            for a, b in sp:
                if a >= end:
                    kept += 1
                    end = b
                elif b > end:
                    end = b
            found[canon] += kept
    if found.get("rest api") and not re.search(r"\bapis?\b", text, re.I):
        del found["rest api"]
    return found


def skill_category(skill: str) -> str:
    return SKILLS.get(skill, ("other", []))[0]


# ---------------------------------------------------------------- roles
ROLES = {
    "Software Engineer": {
        "core": ["data structures", "oop", "git", "sql", "rest api"],
        "important": ["python", "java", "javascript", "c++", "system design", "docker", "linux", "unit testing"],
        "nice": ["aws", "microservices", "ci/cd", "agile", "design patterns", "operating systems"],
        "titles": ["software engineer", "software developer", "sde", "developer", "programmer", "engineer"],
        "certs": ["AWS Certified Cloud Practitioner", "Oracle Certified Associate (Java)", "Meta/Coursera Programming specializations"],
    },
    "Full Stack Developer": {
        "core": ["javascript", "react", "node.js", "html", "css", "rest api", "git"],
        "important": ["typescript", "mongodb", "postgresql", "express", "docker", "sql", "next.js"],
        "nice": ["aws", "redis", "graphql", "ci/cd", "tailwind css", "jwt", "unit testing"],
        "titles": ["full stack", "fullstack", "full-stack", "web developer", "mern", "mean"],
        "certs": ["Meta Full-Stack Engineer (Coursera)", "AWS Cloud Practitioner", "freeCodeCamp certifications"],
    },
    "Frontend Developer": {
        "core": ["html", "css", "javascript", "react", "git", "responsive design"],
        "important": ["typescript", "next.js", "tailwind css", "redux", "figma", "unit testing", "vue", "angular"],
        "nice": ["webpack", "vite", "jest", "cypress", "graphql", "design systems"],
        "titles": ["frontend", "front-end", "front end", "ui developer", "react developer", "web developer"],
        "certs": ["Meta Front-End Developer (Coursera)", "freeCodeCamp Responsive Web Design"],
    },
    "Backend Developer": {
        "core": ["rest api", "sql", "git", "database design"],
        "important": ["python", "java", "node.js", "django", "flask", "fastapi", "spring boot", "postgresql", "docker", "redis"],
        "nice": ["microservices", "kafka", "aws", "ci/cd", "jwt", "unit testing", "system design", "grpc"],
        "titles": ["backend", "back-end", "back end", "api developer", "server-side"],
        "certs": ["AWS Developer Associate", "Oracle Java certification", "MongoDB Associate Developer"],
    },
    "Data Analyst": {
        "core": ["sql", "excel", "data analysis", "data visualization", "statistics"],
        "important": ["python", "pandas", "tableau", "power bi", "numpy", "etl"],
        "nice": ["r", "looker", "bigquery", "jupyter", "data warehousing"],
        "titles": ["data analyst", "business analyst", "analytics", "bi analyst", "business intelligence", "insights analyst"],
        "certs": ["Google Data Analytics Certificate", "Microsoft PL-300 (Power BI)", "Tableau Desktop Specialist"],
    },
    "Data Scientist": {
        "core": ["python", "machine learning", "statistics", "pandas", "numpy", "sql"],
        "important": ["scikit-learn", "deep learning", "data visualization", "feature engineering", "tensorflow", "pytorch", "jupyter"],
        "nice": ["nlp", "time series", "xgboost", "mlflow", "apache spark", "r"],
        "titles": ["data scientist", "data science", "applied scientist", "ml scientist"],
        "certs": ["DeepLearning.AI Machine Learning Specialization", "IBM Data Science Professional Certificate", "AWS Machine Learning Specialty"],
    },
    "ML / AI Engineer": {
        "core": ["python", "machine learning", "deep learning", "pytorch", "git"],
        "important": ["tensorflow", "scikit-learn", "nlp", "llm", "docker", "mlops", "computer vision", "numpy", "rest api"],
        "nice": ["rag", "langchain", "hugging face", "vector database", "aws", "kubernetes", "fastapi", "generative ai", "prompt engineering"],
        "titles": ["machine learning", "ml engineer", "ai engineer", "ai/ml", "deep learning", "nlp engineer", "llm", "genai", "generative ai"],
        "certs": ["DeepLearning.AI Deep Learning Specialization", "AWS Machine Learning Specialty", "Google Professional ML Engineer"],
    },
    "Data Engineer": {
        "core": ["sql", "python", "etl", "data warehousing", "git"],
        "important": ["apache spark", "airflow", "kafka", "aws", "postgresql", "docker", "snowflake", "bigquery", "dbt"],
        "nice": ["hadoop", "kubernetes", "terraform", "ci/cd", "database design", "mongodb"],
        "titles": ["data engineer", "etl developer", "analytics engineer", "big data"],
        "certs": ["Databricks Data Engineer Associate", "Google Professional Data Engineer", "AWS Data Engineer Associate"],
    },
    "DevOps / Cloud Engineer": {
        "core": ["linux", "docker", "git", "ci/cd", "aws"],
        "important": ["kubernetes", "terraform", "jenkins", "github actions", "bash", "python", "ansible", "nginx"],
        "nice": ["azure", "gcp", "prometheus", "grafana", "helm", "serverless", "computer networks"],
        "titles": ["devops", "cloud engineer", "sre", "site reliability", "platform engineer", "infrastructure"],
        "certs": ["AWS Solutions Architect Associate", "CKA (Kubernetes)", "HashiCorp Terraform Associate", "Azure AZ-104"],
    },
    "Cybersecurity Analyst": {
        "core": ["cybersecurity", "network security", "linux", "computer networks", "owasp"],
        "important": ["penetration testing", "wireshark", "nmap", "siem", "incident response", "vulnerability assessment", "burp suite", "cryptography"],
        "nice": ["metasploit", "kali linux", "python", "bash", "soc", "aws"],
        "titles": ["security", "cyber", "soc analyst", "penetration", "infosec", "vapt"],
        "certs": ["CompTIA Security+", "CEH", "eJPT", "Google Cybersecurity Certificate", "OSCP (advanced)"],
    },
    "Mobile App Developer": {
        "core": ["git", "rest api", "oop"],
        "important": ["android", "kotlin", "flutter", "dart", "react native", "ios", "swift", "firebase"],
        "nice": ["jetpack compose", "swiftui", "sqlite", "ci/cd", "unit testing", "figma"],
        "titles": ["android", "ios", "mobile", "flutter", "react native", "app developer"],
        "certs": ["Associate Android Developer (legacy)", "Meta Android/iOS Developer (Coursera)", "Flutter Foundations"],
    },
    "QA / Test Engineer": {
        "core": ["manual testing", "test automation", "sql", "agile"],
        "important": ["selenium", "postman", "java", "python", "jira", "bug tracking", "rest api", "cypress", "playwright"],
        "nice": ["jenkins", "ci/cd", "pytest", "junit", "git"],
        "titles": ["qa", "tester", "test engineer", "sdet", "quality assurance", "automation engineer"],
        "certs": ["ISTQB Foundation", "Selenium/Cypress course certificates"],
    },
    "UI / UX Designer": {
        "core": ["figma", "ui/ux", "wireframing", "prototyping", "user research"],
        "important": ["design systems", "adobe xd", "photoshop", "responsive design", "html", "css"],
        "nice": ["agile", "jira", "javascript"],
        "titles": ["ui", "ux", "product designer", "interaction designer", "visual designer", "designer"],
        "certs": ["Google UX Design Certificate", "Interaction Design Foundation courses", "NN/g UX Certification"],
    },
    "Research Intern / Scientist": {
        "core": ["python", "machine learning", "statistics", "research", "academic writing"],
        "important": ["deep learning", "pytorch", "numpy", "publications", "nlp", "computer vision", "data analysis"],
        "nice": ["tensorflow", "reinforcement learning", "matlab", "r", "jupyter", "mlflow"],
        "titles": ["research", "scientist", "phd", "research intern", "research assistant", "r&d"],
        "certs": ["DeepLearning.AI specializations", "NPTEL (relevant IIT courses)", "Coursera Mathematics for ML"],
    },
}
DEFAULT_ROLE = "Software Engineer"


def normalize_role(role: str | None) -> str:
    if not role:
        return DEFAULT_ROLE
    r = role.strip().lower()
    for name in ROLES:
        if name.lower() == r:
            return name
    legacy = {"ai/ml": "ML / AI Engineer", "ml engineer": "ML / AI Engineer", "devops": "DevOps / Cloud Engineer",
              "cloud": "DevOps / Cloud Engineer", "cyber": "Cybersecurity Analyst", "ui/ux": "UI / UX Designer",
              "qa": "QA / Test Engineer", "sde": "Software Engineer", "web": "Full Stack Developer"}
    for k, v in legacy.items():
        if k in r:
            return v
    for name in ROLES:
        if r in name.lower() or name.lower() in r:
            return name
    return DEFAULT_ROLE


def role_weights(role: str) -> dict[str, int]:
    p = ROLES[normalize_role(role)]
    w = {}
    for s in p["nice"]:
        w[s] = 1
    for s in p["important"]:
        w[s] = 2
    for s in p["core"]:
        w[s] = 3
    return w
