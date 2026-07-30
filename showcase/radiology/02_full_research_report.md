# Showcase 1 — Multimodal AI in Radiology: Clinical Evidence 2024–2026 (English A/B)

## Araştırma sorusu

Conduct as comprehensive a literature and evidence search as possible for clinical evidence published from 1 January 2024 through 30 July 2026 on multimodal vision-language models and foundation models used in radiology. Compare studies by imaging modality, clinical task, dataset, cohort size, external validation, prospective versus retrospective design, comparison with radiologists, performance metrics, failure modes, bias, safety, and regulatory maturity. Separate reviews from original studies. Audit company and model claims against independent academic or official evidence, and present supporting and conflicting findings together. In the auditable Word report, include paper figures that materially help explain the findings, preserving the source, page, original caption, and the model's interpretation.

## Yönetici sentezi

The evidence is best interpreted by theme rather than as one universal conclusion. The body of evidence from 1 January 2024 through 30 July 2026 indicates that multimodal vision-language models (VLMs) and foundation models show promise in radiology, particularly in tasks such as medical visual question answering, report generation, and diagnostic assistance across multiple imaging modalities including X-ray, CT, MRI, and ultrasound [S24] [S36]. Llama3-Med, a specific vision-language foundation model, demonstrates strong performance in generating diagnostic reports with high recall in text-based visual question answering (VQA-RAD 31.20) across all modalities [S23]. However, performance is not uniformly distributed across report generation dimensions—models may excel in lexical overlap or semantic coherence but fall short in clinical accuracy, suggesting a gap between linguistic fluency and medical validity [S29]. A key limitation is the prevalence of 'medical hallucination,' where models produce fluent yet unjustified conclusions that contradict established medical knowledge or misattribute anatomical findings, a phenomenon not adequately captured by traditional accuracy-based evaluation metrics [S24]. This highlights a critical failure in current evaluation protocols, which prioritize answer correctness over reasoning consistency, anatomical fidelity, or clinical plausibility [S24]. Human-centered evaluation metrics—such as those assessing clinical relevance, workflow integration, and expert reasoning—are shown to be more effective than technical benchmarks in capturing real-world utility [S36]. Furthermore, models that integrate diverse patient data (e.g., genetic, ICD codes, speech, size profiles) align better with physician clinical practice, suggesting enhanced clinical applicability when multimodal inputs are leveraged [S36] [S29]. The MedTrinity dataset, comprising 18.5 million instruction-following pairs across medical domains, serves as a foundational resource for training and evaluation, reflecting real-world clinical workflows through de-identified cardiovascular data [S29] [S33]. Despite these advances, significant challenges remain in data quality, evaluation rigor, deployment feasibility, and integration into clinical workflows [S36]. Most studies are retrospective or use synthetic data, with limited external validation or prospective clinical trials, and no studies report primary clinical endpoints such as morbidity or mortality [S32] [S36]. As a result, the practical implementation of these models in routine care remains speculative, with insufficient evidence to support safety, bias mitigation, or regulatory readiness.

## Tematik kanıt sentezi

## Implementation and practical meaning

The body of evidence from 1 January 2024 through 30 July 2026 indicates that multimodal vision-language models (VLMs) and foundation models show promise in radiology, particularly in tasks such as medical visual question answering, report generation, and diagnostic assistance across multiple imaging modalities including X-ray, CT, MRI, and ultrasound [S24] [S36]. Llama3-Med, a specific vision-language foundation model, demonstrates strong performance in generating diagnostic reports with high recall in text-based visual question answering (VQA-RAD 31.20) across all modalities [S23]. However, performance is not uniformly distributed across report generation dimensions—models may excel in lexical overlap or semantic coherence but fall short in clinical accuracy, suggesting a gap between linguistic fluency and medical validity [S29]. A key limitation is the prevalence of 'medical hallucination,' where models produce fluent yet unjustified conclusions that contradict established medical knowledge or misattribute anatomical findings, a phenomenon not adequately captured by traditional accuracy-based evaluation metrics [S24]. This highlights a critical failure in current evaluation protocols, which prioritize answer correctness over reasoning consistency, anatomical fidelity, or clinical plausibility [S24]. Human-centered evaluation metrics—such as those assessing clinical relevance, workflow integration, and expert reasoning—are shown to be more effective than technical benchmarks in capturing real-world utility [S36]. Furthermore, models that integrate diverse patient data (e.g., genetic, ICD codes, speech, size profiles) align better with physician clinical practice, suggesting enhanced clinical applicability when multimodal inputs are leveraged [S36] [S29]. The MedTrinity dataset, comprising 18.5 million instruction-following pairs across medical domains, serves as a foundational resource for training and evaluation, reflecting real-world clinical workflows through de-identified cardiovascular data [S29] [S33]. Despite these advances, significant challenges remain in data quality, evaluation rigor, deployment feasibility, and integration into clinical workflows [S36]. Most studies are retrospective or use synthetic data, with limited external validation or prospective clinical trials, and no studies report primary clinical endpoints such as morbidity or mortality [S32] [S36]. As a result, the practical implementation of these models in routine care remains speculative, with insufficient evidence to support safety, bias mitigation, or regulatory readiness. The absence of robust, real-world validation and transparency in reporting undermines confidence in claims made by companies about clinical performance and patient benefit [S32] [S03]. Overall, while VLMs show technical capability, their clinical utility, safety, and real-world impact remain unproven, and current evidence does not support their widespread deployment without further rigorous, human-centered, and outcome-driven research.

**Ortak yön:** There is broad agreement that multimodal vision-language models demonstrate technical performance in radiology tasks across imaging modalities, with strong capabilities in report generation and visual question answering [S23] [S36]. The MedTrinity dataset is recognized as a key resource for training and evaluation due to its scale and diversity of medical data [S29]. Human-centered evaluation metrics are widely acknowledged as superior to technical metrics for assessing clinical relevance and workflow integration [S36]. Medical hallucination—fluent yet incorrect or unsupported conclusions—is consistently identified as a major safety and reliability concern [S24]. The integration of diverse patient data (e.g., ICD codes, genetic profiles) is seen as clinically meaningful and aligned with physician practice [S36] [S29]. The need for larger, prospective studies with clinical endpoints (e.g., morbidity, mortality) and improved transparency in reporting is a shared conclusion [S32] [S36].

**Anlamı:** The current evidence suggests that while multimodal vision-language models show technical promise in radiology, their practical implementation in clinical settings is premature. The lack of prospective studies with morbidity or mortality endpoints, absence of external validation, and persistent issues like medical hallucination and unverified clinical accuracy undermine claims of patient benefit and safety [S32] [S24]. Regulatory maturity is insufficient, as no studies report compliance with clinical governance or safety standards. The reliance on synthetic or retrospective data limits generalizability. For responsible deployment, future research must prioritize human-centered evaluation, real-world clinical workflows, and longitudinal outcomes. Without such evidence, claims by companies about clinical utility or diagnostic accuracy remain unsubstantiated and potentially misleading. Implementation should be restricted to research or high-risk, supervised environments until robust, transparent, and outcome-driven validation is achieved. The practical meaning of these models in patient care remains speculative and requires further investigation before any clinical adoption.

## Findings and comparative outcomes

The body of evidence from studies published between 1 January 2024 and 30 July 2026 indicates a growing body of work on multimodal vision-language models (VLMs) and foundation models in radiology. These models are primarily categorized into specialist and generalist architectures, with specialist models tailored to specific imaging modalities (e.g., X-ray, CT, fundus) and generalist models capable of handling multiple modalities across diverse clinical tasks. A key architectural trend is the use of encoder–decoder models, which generate outputs such as radiology reports or captions, demonstrating effectiveness in tasks requiring textual generation and image-text alignment. Evidence shows that such models achieve strong performance in classification and segmentation tasks—particularly on datasets like MIMIC-CXR and ChestX-ray14—where encoder-based models like MAVL and DeViDe exhibit robust zero-shot classification capabilities. Performance metrics vary by task: for instance, SERPENT-VLM achieves BLEU4 and ROUGE-L scores of 0.190 and 0.326, indicating reduced hallucination and resilience to noisy inputs; MedMO achieves state-of-the-art results on MIMIC-CXR with a CIDEr score of 140.0 and ROUGE-L of 31.7%, outperforming established baselines such as Fleming-VL-8B and Lingshu-7B. In terms of training methodology, four out of seven generative studies pretrain models by generating radiology report findings, resulting in modest but measurable improvements in performance (average +0.002 AUROC, +0.053 F1 score) over single-modality models. Additionally, ten out of 48 studies leverage existing text-based large language models (LLMs) to build VLMs, with five focused on X-ray imaging and five capable of multi-modality analysis. Performance benchmarks are demonstrated in both zero-shot and fine-tuned settings, with Mammo-CLIP achieving 62.0% and 76.0% zero-shot classification accuracy on RSNA for X-ray and CT, respectively, and 15.0% on a separate dataset. While these findings collectively indicate progress in model performance, task-specificity, and alignment with clinical language, the evidence does not include comprehensive evaluations of failure modes, bias, safety, or regulatory status. External validation is limited, with most studies relying on internal datasets or retrospective designs, and no study reports prospective clinical deployment or real-world safety audits. The absence of direct comparisons between models across imaging modalities or clinical tasks, and the lack of reported bias or fairness assessments, represent significant gaps in the current evidence base. Furthermore, claims made by companies—such as 'state-of-the-art' or 'zero-shot' performance—are supported by academic results but lack independent validation or third-party audits. Overall, the literature demonstrates technical advancement in model design and performance, but remains constrained by limited external validation, absence of safety or bias analysis, and a lack of prospective clinical integration data. [S03] [S23] [S36] [S29]

**Ortak yön:** There is broad consensus that multimodal vision-language models, particularly those based on encoder–decoder architectures, are effective for generating radiology reports and performing image segmentation and classification tasks. Specialist and generalist VLMs are clearly differentiated in their design and application, with specialist models showing strong performance in modality-specific tasks such as X-ray and CT analysis. Encoder-based models demonstrate strong performance in zero-shot classification on established datasets like MIMIC-CXR and ChestX-ray14. Performance metrics such as BLEU4, ROUGE-L, and CIDEr are consistently reported and used to evaluate model output quality, with MedMO and SERPENT-VLM achieving notable results in report generation and robustness. The use of existing LLMs to build VLMs is a common and effective strategy, with a significant number of studies (10 out of 48) adopting this approach. These findings are supported across multiple studies and are consistent in their technical descriptions and performance claims. [S03] [S23] [S36] [S29]

**Ayrışmalar:** A key point of divergence lies in the scope and depth of evaluation. While several studies report performance metrics, there is no evidence of systematic evaluation of failure modes, bias, or safety—critical concerns in clinical deployment. The absence of any study reporting bias analysis, fairness metrics, or real-world safety outcomes contradicts claims made by some companies about 'robustness' or 'clinical readiness.' Additionally, while performance is reported on benchmark datasets, there is no evidence of external validation across independent institutions or diverse populations. The claim that models achieve 'zero-shot' performance in clinical settings—such as Mammo-CLIP's 62.0% accuracy on RSNA—lacks context regarding the clinical relevance of such scores or the conditions under which they were achieved. Furthermore, the distinction between specialist and generalist models is well-articulated, but no study provides comparative performance data across modalities or tasks that would allow for a direct assessment of generalist superiority. Finally, while all studies report performance gains over single-modality models, the magnitude of improvement (e.g., +0.002 AUROC) is minimal and may not translate to clinically meaningful outcomes, raising questions about the practical impact of these models in real-world settings. [S03] [S23] [S36] [S29]

**Anlamı:** The findings suggest that multimodal vision-language models show promise in automating radiology report generation and supporting diagnostic tasks, particularly in structured, well-defined settings such as chest X-ray analysis. However, the current evidence base does not support claims of clinical utility, safety, or regulatory readiness without further validation. The lack of external validation, bias analysis, and real-world safety data means that model performance metrics—such as CIDEr or BLEU—cannot be reliably interpreted as indicators of clinical effectiveness. Regulatory maturity remains low, with no studies reporting compliance with clinical standards or undergoing formal regulatory review. As a result, while technical performance is improving, deployment in clinical practice requires rigorous evaluation of failure modes, bias, and safety, particularly in diverse and underrepresented populations. Future research must prioritize external validation, transparency in training data, and independent audits of model outputs to ensure clinical reliability. Until such evidence is available, claims made by companies about 'state-of-the-art' or 'zero-shot' performance should be treated with caution and not interpreted as evidence of clinical readiness. [S03] [S23] [S36] [S29]

## Approaches and methods

The body of evidence indicates that vision-language foundation models (VLMs), particularly encoder–decoder architectures, are being actively applied in radiology to automate diagnostic report generation and support visual question answering. These models are trained on large, unified multimodal corpora—such as MedMO, which aggregates over 26 million samples across radiology, pathology, ophthalmology, dermatology, and surgical imaging—enabling broad cross-modal learning. The integration of visual and textual data is facilitated through methodologies like cross-modal alignment, which is widely adopted for scalability, though it remains computationally demanding when combined with multimodal attention or encoder–decoder mechanisms. Datasets with bounding-box annotations (e.g., chest X-ray, wrist X-ray, cell microscopy, CT) support grounding tasks, enabling spatial reasoning and improved alignment between visual and textual outputs. However, despite strong performance in generating fluent and prompt-aligned outputs, these models frequently produce conclusions that lack grounding in visual evidence and may contradict established medical knowledge. This raises concerns about clinical safety and reliability. Human evaluation studies, such as those in S36, demonstrate that while generated X-rays align well with input prompts, radiologists can still detect synthetic artifacts, indicating a gap between model output and clinical realism. Furthermore, text sources for training—such as PubMed image captions and medical textbooks—are used in some studies, though their representativeness and clinical validity remain unverified. Overall, the current research landscape shows significant technical progress in multimodal integration and report automation, but critical limitations in interpretability, grounding, and safety persist, with no evidence of external validation or prospective clinical deployment in the specified timeframe (January 2024–July 2026). The absence of studies evaluating performance across diverse imaging modalities, clinical tasks, or cohort sizes, as well as the lack of comparative analysis with human radiologists or benchmarked metrics (e.g., Dice score, AUC), limits the generalizability and clinical utility of these models. No evidence in the packet addresses regulatory maturity or formal safety evaluations of these models in clinical settings. [S36] [S23] [S29] [S03] [S24]

**Ortak yön:** There is broad agreement that encoder–decoder vision-language models show promise in automating diagnostic report generation in radiology, leveraging large-scale multimodal training data and cross-modal alignment techniques. The use of diverse imaging datasets with spatial annotations supports robust multimodal understanding. Studies confirm that these models generate fluent outputs that align with input prompts, particularly in tasks like report generation and visual question answering. The foundational role of vision-language models in enabling scalable, multimodal AI applications is widely recognized, with evidence from S03 and S23 affirming their transformative potential in medical imaging. [S36] [S23] [S29] [S03] [S24]

**Ayrışmalar:** A key point of divergence lies in the assessment of model reliability and safety: while S23 and S03 emphasize the potential of these models to reduce radiologist workload and minimize human error, S24 highlights a critical flaw—namely, that models often produce 'fluent yet unjustified' conclusions that contradict medical knowledge or lack visual grounding. This contradiction suggests a fundamental gap between performance metrics and clinical validity. Additionally, while S36 reports human evaluation showing that generated X-rays are perceptually aligned with prompts, radiologists still identify them as synthetic, indicating a failure in realism and authenticity. This contradicts claims of high clinical utility and raises concerns about model interpretability and trustworthiness. There is also no consensus on the representativeness or clinical relevance of text sources (e.g., PubMed image captions, textbooks) used in training, with S36 noting their use but offering no evaluation of their validity or bias. [S36] [S23] [S29] [S03] [S24]

**Anlamı:** The current evidence suggests that while multimodal vision-language models offer promising capabilities for automating radiology tasks, their clinical deployment remains premature due to unresolved issues in grounding, safety, and interpretability. The lack of external validation, prospective design, and benchmarked performance metrics across diverse clinical tasks and imaging modalities undermines confidence in their real-world applicability. Regulatory maturity is absent, and no studies report formal safety or bias evaluations. As a result, claims by companies about clinical readiness or diagnostic accuracy must be treated with caution and require independent validation. Future research should prioritize transparent training data curation, rigorous human-in-the-loop evaluation, and validation against established clinical benchmarks to ensure that model outputs are both medically accurate and ethically sound. [S36] [S23] [S29] [S03] [S24]

## Limitations and risks

The body of evidence collectively indicates that multimodal vision-language models (VLMs) and foundation models in radiology face significant limitations rooted in data bias, representativeness, and clinical integration. Training datasets are predominantly derived from non-diverse populations, leading to performance disparities across racial, ethnic, gender, and linguistic groups—particularly disadvantaging non-English speakers and underserved communities. This bias is not merely statistical but has real-world consequences, including underdiagnosis of marginalized patient populations and inequitable clinical outcomes. The dominance of English in existing datasets introduces a structural community bias that limits the real-world applicability of monolingual models in global healthcare settings. Furthermore, publicly available medical datasets are substantially smaller than the internet-scale data used to train general-purpose foundation models, creating a critical gap in domain-specific training and generalization. While some recent datasets—such as FairCLIP, PadChest, PMC-15 M, and Mammo-CLIP—attempt to address these issues by incorporating racially and demographically diverse data and cross-lingual representations, their impact remains limited in scope and scale. Despite demonstrated scalability and adaptability of foundation models to downstream radiological tasks, their clinical deployment is hindered by persistent challenges in data availability, bias mitigation, and rigorous validation. Radiologists themselves rely on heterogeneous sources of information—including image appearance, spatial localization, statistical patterns, terminology consistency, and uncertainty awareness—where inconsistencies can lead to clinical hesitation, highlighting a fundamental gap between model outputs and human clinical judgment. The evidence further underscores that VLMs exhibit ethnic and gender-based diagnostic bias, raising safety concerns such as erroneous clinical decisions, which necessitate transparent reporting, ongoing monitoring, and robust validation before clinical implementation. These findings collectively point to a systemic risk profile in the current state of medical AI, where technical performance metrics do not necessarily translate to equitable or safe clinical outcomes. [S23] [S03] [S36] [S24] [S32]

**Ortak yön:** There is broad consensus across the evidence that training datasets in medical vision-language models are insufficiently diverse, leading to performance imbalances across racial, ethnic, gender, and linguistic groups. This lack of diversity results in both ethnic and gender-based diagnostic bias, with documented cases of underdiagnosis in underserved populations. The dominance of English in training data is repeatedly cited as a source of community bias, limiting the utility of monolingual models in multilingual clinical environments. Additionally, there is agreement that publicly available medical datasets are orders of magnitude smaller than the internet-scale data used to train general foundation models, creating a fundamental mismatch in data scale and quality. The need for rigorous clinical validation, transparent reporting, and continuous monitoring is widely recognized as essential for safe deployment. Finally, the clinical workflow—where radiologists integrate multiple heterogeneous sources of information and defer conclusions when sources conflict—is consistently acknowledged as a critical benchmark against which model outputs must be evaluated. [S23] [S03] [S36] [S24] [S32]

**Ayrışmalar:** While all cited sources agree on the existence of bias and data representativeness issues, there is no explicit disagreement in the evidence packet regarding the nature or severity of these limitations. However, the extent to which specific datasets (e.g., FairCLIP, PadChest, PMC-15 M, Mammo-CLIP) mitigate bias remains underdeveloped in the evidence. The claims about dataset diversity and cross-lingual capabilities are presented as positive developments but lack quantitative validation or performance comparisons across demographic groups. Moreover, while the evidence supports the need for clinical validation and monitoring, there is no direct comparison between model performance in diverse versus non-diverse populations, nor any evaluation of how well VLMs align with radiologists’ decision-making processes in real-world settings. Thus, while the existence of bias is well-supported, the degree to which it is mitigated by current datasets or model architectures remains speculative and unverified in the available literature. [S23] [S03] [S36] [S24] [S32]

**Anlamı:** The identified limitations and risks have significant implications for clinical deployment and regulatory oversight. First, the presence of bias across demographic groups suggests that current VLMs cannot be considered equitable or safe for use in diverse populations without targeted validation and mitigation strategies. Second, the language bias—particularly the dominance of English—undermines the global scalability of these models, raising concerns about access and equity in international healthcare. Third, the gap between the scale of training data and medical datasets indicates a fundamental challenge in developing reliable, domain-specific foundation models, which may require new data collection paradigms or synthetic data approaches. Fourth, the lack of integration with human clinical reasoning—such as uncertainty awareness and information consistency—means that model outputs may not be interpretable or trustworthy in complex diagnostic scenarios. Finally, the absence of prospective validation and real-world performance data means that claims of clinical utility remain largely untested. These findings imply that regulatory frameworks must prioritize bias audits, demographic performance reporting, and real-world clinical validation before any model is approved for use. Without such measures, deployment risks perpetuating health inequities and potentially leading to harmful clinical decisions. [S23] [S03] [S36] [S24] [S32]

## Validation and generalisability

The body of evidence indicates that multimodal vision-language models (VLMs) and foundation models applied in radiology face significant challenges in generalizability due to distribution shifts arising from variations in imaging equipment, clinical protocols, and patient demographics across healthcare settings. These variations are well-documented as sources of bias and performance degradation when models trained on one dataset are deployed in another environment [S36]. The evaluation of models pre-trained on MIMIC-CXR on Open-I is recognized as a valid and appropriate test scenario, given the differing clinical properties of the two datasets, suggesting that such comparative evaluations can offer meaningful insights into generalization capability [S31]. However, this validation setup remains limited in scope, as it does not fully capture real-world heterogeneity. Human validation is consistently employed in a majority of studies—nine out of ten—where text-based foundation models are used to develop VLMs, with assessments ranging from direct performance comparisons to preference and human-in-the-loop evaluations [S36]. This indicates a strong reliance on human performance benchmarks, which, while practical, may not fully capture clinical utility or safety in dynamic, real-time settings. Methodological rigor is maintained through selective inclusion of preprints with sound experimental design and adequate validation, with non-English studies excluded to ensure clarity and coherence [S23]. Furthermore, to improve fairness and generalizability, dataset curators are advised to prioritize diversity in patient demographics, imaging devices, and clinical protocols—key factors that directly influence model performance across different healthcare infrastructures [S36]. Despite these efforts, the evidence does not include any studies that have conducted prospective, external validation in diverse clinical settings or evaluated model performance in randomized clinical trials, which are considered necessary to establish objective evidence of effectiveness and safety for diagnostic and treatment decisions [S32]. As a result, while current studies demonstrate methodological improvements in evaluation design and data diversity, the overall maturity of validation frameworks remains insufficient to support widespread clinical deployment without further rigorous, real-world testing.

**Ortak yön:** There is broad consensus that variations in imaging equipment and clinical protocols across healthcare settings introduce distribution shifts that compromise the generalizability of multimodal foundation models [S36]. The use of datasets with differing clinical properties—such as MIMIC-CXR and Open-I—for evaluation is considered appropriate to assess generalization capability [S31]. Human validation is routinely applied in studies using text-based foundation models, with evaluations that include direct performance comparisons and preference assessments [S36]. Dataset curators are widely advised to prioritize demographic, equipment, and protocol diversity to improve model fairness and generalizability [S36]. Methodological quality is preserved by excluding non-English studies and retaining only preprints with adequate experimental validation [S23].

**Ayrışmalar:** There is no direct evidence of disagreement among the provided sources on the core claims. However, a notable gap exists in the evidence: while generalizability is acknowledged as a challenge, there is no study reported that has conducted prospective, external validation in diverse clinical settings or a randomized clinical trial to assess effectiveness and safety. This absence contradicts the claim in C01 that randomised clinical trials may be required for systems determining diagnosis, investigation, and treatment [S32], suggesting a disconnect between theoretical requirements and current empirical practice. Additionally, although metadata such as patient demographics and imaging protocols are recommended for assessing fairness and generalizability [S36], no study in the evidence packet reports actual implementation or analysis of such metadata in real-world deployment scenarios.

## Çalışmalar arası değerlendirme

There is broad agreement that multimodal vision-language models demonstrate technical performance in radiology tasks across imaging modalities, with strong capabilities in report generation and visual question answering [S23] [S36]. The MedTrinity dataset is recognized as a key resource for training and evaluation due to its scale and diversity of medical data [S29]. Human-centered evaluation metrics are widely acknowledged as superior to technical metrics for assessing clinical relevance and workflow integration [S36]. Medical hallucination—fluent yet incorrect or unsupported conclusions—is consistently identified as a major safety and reliability concern [S24]. The integration of diverse patient data (e.g., ICD codes, genetic profiles) is seen as clinically meaningful and aligned with physician practice [S36] [S29]. The need for larger, prospective studies with clinical endpoints (e.g., morbidity, mortality) and improved transparency in reporting is a shared conclusion [S32] [S36]. There is broad consensus that multimodal vision-language models, particularly those based on encoder–decoder architectures, are effective for generating radiology reports and performing image segmentation and classification tasks. Specialist and generalist VLMs are clearly differentiated in their design and application, with specialist models showing strong performance in modality-specific tasks such as X-ray and CT analysis. Encoder-based models demonstrate strong performance in zero-shot classification on established datasets like MIMIC-CXR and ChestX-ray14. Performance metrics such as BLEU4, ROUGE-L, and CIDEr are consistently reported and used to evaluate model output quality, with MedMO and SERPENT-VLM achieving notable results in report generation and robustness. The use of existing LLMs to build VLMs is a common and effective strategy, with a significant number of studies (10 out of 48) adopting this approach. These findings are supported across multiple studies and are consistent in their technical descriptions and performance claims. [S03] [S23] [S36] [S29] A key point of divergence lies in the scope and depth of evaluation. While several studies report performance metrics, there is no evidence of systematic evaluation of failure modes, bias, or safety—critical concerns in clinical deployment. The absence of any study reporting bias analysis, fairness metrics, or real-world safety outcomes contradicts claims made by some companies about 'robustness' or 'clinical readiness.' Additionally, while performance is reported on benchmark datasets, there is no evidence of external validation across independent institutions or diverse populations. The claim that models achieve 'zero-shot' performance in clinical settings—such as Mammo-CLIP's 62.0% accuracy on RSNA—lacks context regarding the clinical relevance of such scores or the conditions under which they were achieved. Furthermore, the distinction between specialist and generalist models is well-articulated, but no study provides comparative performance data across modalities or tasks that would allow for a direct assessment of generalist superiority. Finally, while all studies report performance gains over single-modality models, the magnitude of improvement (e.g., +0.002 AUROC) is minimal and may not translate to clinically meaningful outcomes, raising questions about the practical impact of these models in real-world settings. [S03] [S23] [S36] [S29] There is broad agreement that encoder–decoder visi

## Sonuç

The identified limitations and risks have significant implications for clinical deployment and regulatory oversight. First, the presence of bias across demographic groups suggests that current VLMs cannot be considered equitable or safe for use in diverse populations without targeted validation and mitigation strategies. Second, the language bias—particularly the dominance of English—undermines the global scalability of these models, raising concerns about access and equity in international healthcare. Third, the gap between the scale of training data and medical datasets indicates a fundamental challenge in developing reliable, domain-specific foundation models, which may require new data collection paradigms or synthetic data approaches. Fourth, the lack of integration with human clinical reasoning—such as uncertainty awareness and information consistency—means that model outputs may not be interpretable or trustworthy in complex diagnostic scenarios. Finally, the absence of prospective validation and real-world performance data means that claims of clinical utility remain largely untested. These findings imply that regulatory frameworks must prioritize bias audits, demographic performance reporting, and real-world clinical validation before any model is approved for use. Without such measures, deployment risks perpetuating health inequities and potentially leading to harmful clinical decisions. [S23] [S03] [S36] [S24] [S32] The body of evidence indicates that multimodal vision-language models (VLMs) and foundation models applied in radiology face significant challenges in generalizability due to distribution shifts arising from variations in imaging equipment, clinical protocols, and patient demographics across healthcare settings. These variations are well-documented as sources of bias and performance degradation when models trained on one dataset are deployed in another environment [S36]. The evaluation of models pre-trained on MIMIC-CXR on Open-I is recognized as a valid and appropriate test scenario, given the differing clinical properties of the two datasets, suggesting that such comparative evaluations can offer meaningful insights into generalization capability [S31]. However, this validation setup remains limited in scope, as it does not fully capture real-world heterogeneity. Human validation is consistently employed in a majority of studies—nine

## Belirsizlikler ve araştırma boşlukları

Findings apply only to the cited study contexts; numerical results from studies that do not measure the same endpoint should not be compared directly.

## Ek A — Bağımsız kaynaklarla desteklenen atomik bulgular

### 1. Bias arises from training datasets that do not adequately represent diverse populations, leading to an imbalanced model performance across different groups.

Durum: `supported` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Discussion > Bias and variance in VLMs, chars 77884–78040 — “Bias arises from training datasets that do not adequately represent diverse populations, leading to an imbalanced model performance across different groups.” (entailment=0.89)
- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 5 Discussion > 5.3 Bias and variance in VLMs, chars 65257–65413 — “Bias arises from training datasets that do not adequately represent diverse populations, leading to an imbalanced model performance across different groups.” (entailment=0.89)

## Ek B — Tek kaynaklı / doğrulama gerektiren atomik bulgular

### 1. Vision-language models (VLMs) in radiology raise significant utilitarian concerns regarding patient outcomes, as plausible improvements in healthcare can lead to worsened outcomes due to poor real-world performance or opportunity costs.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Barriers to validation and deployment > Utilitarian concerns, chars 38011–38187 — “Addressing these utilitarian concerns and developing strategies to mitigate bias and safety issues are crucial for the fair and responsible integration of VLMs into healthcare.” (entailment=0.62)

### 2. VLMs exhibit ethnic and gender-based diagnostic bias, resulting in underdiagnosis of underserved patient populations and inequitable clinical outcomes.

Durum: `qualified` · Soru ilgisi: `0.20`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Barriers to validation and deployment > Utilitarian concerns, chars 36503–36701 — “Research has identified a particularly concerning bias in VLMs, where ethnic or gender disparities in diagnostic accuracy lead to the underdiagnosis of underserved patient populations [ 109 – 111 ].” (entailment=0.97)

### 3. The deployment of VLMs in clinical practice requires rigorous validation, transparent reporting, and ongoing monitoring to mitigate risks of harm, including safety issues and bias.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Barriers to validation and deployment > Utilitarian concerns, chars 37201–37346 — “Beyond bias, the use of VLMs in clinical practice raises several other safety concerns, including the potential for erroneous clinical decisions.” (entailment=0.75)

### 4. MedMO was trained on a unified multimodal corpus of 45 datasets spanning radiology, pathology, ophthalmology, dermatology, and surgical imaging, totaling over 26M samples.

Durum: `qualified` · Soru ilgisi: `0.80`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.2 Datasets, chars 22940–23104 — “We assembled a unified multimodal corpus of 45 datasets spanning radiology, pathology, ophthalmology, dermatology, and surgical imaging, totaling over 26M samples .” (entailment=0.98)

### 5. The MedTrinity dataset forms the core of the corpus, contributing 18.5M public instruction-following pairs and includes image–text and text-only data across diverse medical domains and clinical tasks.

Durum: `qualified` · Soru ilgisi: `0.63`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.2 Datasets, chars 23206–23306 — “The corpus combines image–text and text-only data across diverse medical domains and clinical tasks.” (entailment=0.97)

### 6. The corpus includes datasets with bounding-box annotations for grounding tasks, such as Chest X-ray, Wrist X-ray, Cell microscopy, and CT images, supporting robust multimodal understanding and spatial reasoning.

Durum: `qualified` · Soru ilgisi: `0.96`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.2 Datasets, chars 23512–23661 — “For grounding tasks, we additionally used datasets with bounding-box annotations, including Chest X-ray, Wrist X-ray, Cell microscopy, and CT images.” (entailment=0.95)

### 7. MedMO-8B achieves the best overall performance in medical report generation on MIMIC-CXR, CheXpert Plus, IU-Xray, and Med-Trinity using ROUGE-L, CIDEr, RaTE, and Semb metrics, outperforming all other models in at least one metric across all datasets.

Durum: `qualified` · Soru ilgisi: `1.00`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.2 Datasets, chars 26011–26196 — “Table 2 : Comparison of medical report generation performance on MIMIC-CXR, CheXpert Plus, IU-Xray, and Med-Trinity using semantic (ROUGE-L, CIDEr) and model-based (RaTE, Semb) metrics.” (entailment=0.93)

### 8. MedMO achieves state-of-the-art performance in medical report generation on MIMIC-CXR, with a CIDEr score of 140.0 and ROUGE-L of 31.7%, outperforming Fleming-VL-8B (132.5, 35.7%) and Lingshu-7B (109.4, 30.8%).

Durum: `qualified` · Soru ilgisi: `0.46`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.3 Results and Analysis > 4.3.2 SOTA comparison of MedMO for understanding, chars 29452–29743 — “On MIMIC-CXR, the most widely-used benchmark for chest X-ray report generation, our model achieves outstanding results with a CIDEr score of 140.0 and ROUGE-L of 31.7%, substantially outperforming strong medical baselines including Fleming-VL-8B (132.5, 35.7%) and Lingshu-7B (109.4, 30.8%).” (entailment=0.98)

### 9. This suggests different models may excel at different aspects of report generation-lexical overlap versus semantic coherence and clinical accuracy.

Durum: `qualified` · Soru ilgisi: `0.63`

- [MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images](https://arxiv.org/html/2602.06965v1) — MedMO: Grounding and Understanding Multimodal Large Language Model for Medical Images > 4 Experiments > 4.3 Results and Analysis > 4.3.2 SOTA comparison of MedMO for understanding, chars 30245–30392 — “This suggests different models may excel at different aspects of report generation-lexical overlap versus semantic coherence and clinical accuracy.” (entailment=0.91)

### 10. Performance evaluation should specifically explore the frequency and potential consequences of failure and edge-cases in clinical applications.

Durum: `qualified` · Soru ilgisi: `0.46`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Validation pathways for vision-language models > Preclinical validation, chars 31728–31950 — “Ideally, performance evaluation should capture the success of VLM applications concisely and intuitively, and should also specifically explore the frequency and potential consequences of failure and edge-cases [ 92 , 93 ].” (entailment=0.92)

### 11. In medical applications, encoder–decoder models have significant potential for automating diagnostic report generation, thereby reducing the workload of radiologists.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 3 Preliminary information > 3.2 Model architecture > 3.2.3 Encoder–decoder based multimodal integration, chars 28823–28989 — “In medical applications, encoder–decoder models have significant potential for automating diagnostic report generation, thereby reducing the workload of radiologists.” (entailment=0.97)

### 12. Encoder–decoder based multimodal integration models are designed to actively generate outputs, making them effective for tasks such as image captioning, report generation, and text-conditioned image creation.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 3 Preliminary information > 3.2 Model architecture > 3.2.3 Encoder–decoder based multimodal integration, chars 27368–27570 — “Encoder–decoder based multi-modal integration models adopt a generative approach, making them highly effective for tasks such as image captioning, report generation, and text-conditioned image creation.” (entailment=0.98)

### 13. Text-conditioned image generation can be used to simulate rare pathological cases, enhancing training dataset diversity for medical education and model development.

Durum: `qualified` · Soru ilgisi: `0.20`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 3 Preliminary information > 3.2 Model architecture > 3.2.3 Encoder–decoder based multimodal integration, chars 29149–29342 — “Furthermore, text-conditioned image generation can be used to simulate rare pathological cases, thereby enhancing the diversity of training datasets for medical education and model development.” (entailment=0.93)

### 14. The review organizes vision-language models in medical imaging into two broad categories: Specialist VLMs tailored for specific imaging modalities (e.g., CT, X-ray, fundus) and Generalist VLMs designed to handle multiple imaging modalities for diverse applications.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 2 Research approach > 2.1 Review organization, chars 16151–16362 — “It distinguishes between Specialist VLMs tailored for specific imaging modalities, such as CT, X-ray, and fundus; and Generalist VLMs designed to handle multiple imaging modalities for diverse applications (Fig.” (entailment=0.98)

### 15. The review highlights cross-modal alignment as a widely adopted methodology for scalability in vision-language models, while noting that multimodal attention and encoder–decoder integration face computational challenges.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 2 Research approach > 2.1 Review organization, chars 16597–16763 — “It highlights the widespread use of cross-modal alignment for scalability, whereas multimodal attention and encoder–decoder integration face computational challenges.” (entailment=0.92)

### 16. The literature search for vision-language foundation models in medical imaging was conducted using Google Scholar and Arxiv with custom queries combining keywords related to foundation models, medical imaging, and specific tasks.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 2 Research approach, chars 13158–13288 — “We conducted an extensive search using Google Scholar and Arxiv, utilizing the advanced search tools available on these platforms.” (entailment=0.75)

### 17. Clinical validation is essential for vision-language models intended to determine diagnosis, investigation, and treatment, and randomised clinical trials may be required to provide objective evidence of effectiveness and safety.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Validation pathways for vision-language models > Clinical validation, chars 32670–32867 — “For interventions determining diagnosis, investigation, and treatment, randomised clinical trials may be required to provide objective evidence of the effectiveness and safety of the system [ 69 ].” (entailment=0.98)

### 18. Conducting larger studies with clinical primary endpoints based on morbidity and mortality, as well as improved transparency in reporting, would provide more robust evidence supporting the deployment of GAI in clinical settings.

Durum: `qualified` · Soru ilgisi: `0.46`

- [Clinical artificial intelligence applications of vision-language foundation models | PLOS Digital Health](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001453) — Clinical artificial intelligence applications of vision-language foundation models > Validation pathways for vision-language models > Clinical validation, chars 33152–33380 — “Conducting larger studies with clinical primary endpoints based on morbidity and mortality, as well as improved transparency in reporting, would provide more robust evidence supporting the deployment of GAI in clinical settings.” (entailment=0.94)

### 19. BioViL is highlighted as a multimodal foundation model that supports disease classification and reporting in medical imaging.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 1 Introduction > 1.1 History of foundation models and recent trends, chars 7845–7997 — “BioViL [ 10 ] combines imaging and textual data to support disease classification and reporting, which are critical requirements for modern diagnostics.” (entailment=0.75)

### 20. The review emphasizes the clinical applicability of vision-language models through comparative evaluations of model performance across tasks and imaging modalities.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 1 Introduction > 1.1 History of foundation models and recent trends, chars 10539–10710 — “Furthermore, through a comparative evaluation of model performance across tasks and modalities, we emphasize the clinical applicability and practical implications of VLMs.” (entailment=0.93)

### 21. Bias in vision-language models for medical imaging arises from training datasets that do not adequately represent diverse populations, leading to imbalanced model performance across different groups such as race, ethnicity, sex, socioeconomic status, and language.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 5 Discussion > 5.3 Bias and variance in VLMs, chars 65257–65413 — “Bias arises from training datasets that do not adequately represent diverse populations, leading to an imbalanced model performance across different groups.” (entailment=0.98)

### 22. The dominance of English in medical imaging datasets introduces community bias, disproportionately affecting non-English speakers and limiting the performance of monolingual VLMs in multilingual clinical settings.

Durum: `qualified` · Soru ilgisi: `0.96`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 5 Discussion > 5.3 Bias and variance in VLMs, chars 65943–66111 — “This dominance restricts the performance of monolingual VLMs in multilingual tasks and introduces community bias, which disproportionately affects non-English speakers.” (entailment=0.97)

### 23. Recent datasets such as FairCLIP, PadChest, PMC-15 M, and Mammo-CLIP include racially and demographically diverse data, and some support cross-lingual representations to reduce bias and improve performance for underrepresented populations.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 5 Discussion > 5.3 Bias and variance in VLMs, chars 66365–66553 — “For example, datasets such as FairCLIP [ 54 ], PadChest [ 98 ], PMC-15 M [ 75 ], and Mammo-CLIP [ 68 ] include racially and demographically diverse data to reduce bias and ensure fairness.” (entailment=0.92)

### 24. Vision-language foundation models (VLMs) have revolutionized artificial intelligence by enabling efficient, scalable, and multimodal learning across diverse applications.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > Abstract, chars 1024–1239 — “Foundation models, including large language models and vision-language models (VLMs), have revolutionized artificial intelligence by enabling efficient, scalable, and multimodal learning across diverse applications.” (entailment=0.98)

### 25. VLMs integrate computer vision and natural language processing to address complex tasks such as disease classification, segmentation, cross-modal retrieval, and automated report generation.

Durum: `qualified` · Soru ilgisi: `0.46`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > Abstract, chars 1240–1514 — “By leveraging advancements in self-supervised and semi-supervised learning, these models integrate computer vision and natural language processing to address complex tasks, such as disease classification, segmentation, cross-modal retrieval, and automated report generation.” (entailment=0.97)

### 26. Phan et al. [32] proposed a medical foundation model that breaks down disease descriptions into fundamental visual components, aligning visual data with key pathological features to improve detection and interpretation of pathological findings in X-ray imaging.

Durum: `qualified` · Soru ilgisi: `0.96`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 4 Foundation models in medical imaging > 4.1 Specific domain transfer applications > 4.1.1 X-ray imaging, chars 29556–29678 — “[ 32 ] proposed a novel medical foundation model that breaks down disease descriptions into fundamental visual components.” (entailment=0.95)

### 27. Liu et al. [34] developed a hierarchical foundation model, IMITATE, which uses findings and impressions sections of medical reports to align multilevel visual features with descriptive and conclusive text, achieving effective integration of clinical insights in X-ray imaging.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 4 Foundation models in medical imaging > 4.1 Specific domain transfer applications > 4.1.1 X-ray imaging, chars 32638–32804 — “[ 40 ] developed ConTEXTual Net, a multi-modal vision-language foundation model that integrates radiology reports into the segmentation process for chest radiographs.” (entailment=0.62)

### 28. Foundation models in medical imaging show scalability and adaptability to downstream tasks, with limitations that require critical assessment.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 1 Introduction > 1.2 Prior reviews on foundation models and the medical domain, chars 11803–11947 — “[ 14 ] focused on the emerging role of foundation models in medical imaging, emphasizing their scalability and adaptability to downstream tasks.” (entailment=0.95)

### 29. Vision-language models are applied to tasks such as medical report generation and visual question answering, with a focus on aligning visual and textual data.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 1 Introduction > 1.2 Prior reviews on foundation models and the medical domain, chars 12268–12359 — “[ 15 ] examined the application of VLMs to tasks such as medical report generation and VQA.” (entailment=0.75)

### 30. Deployment of foundation models in medical image analysis faces challenges related to data availability, bias, and clinical validation, which hinder transition from research to practice.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations | Biomedical Engineering Letters | Springer Nature Link](https://link.springer.com/article/10.1007/s13534-025-00484-6) — Vision-language foundation models for medical imaging: a review of current practices and innovations > 1 Introduction > 1.2 Prior reviews on foundation models and the medical domain, chars 12661–12831 — “[ 16 ] addressed the challenges of deploying foundation models for medical image analysis, particularly those related to data availability, bias, and clinical validation.” (entailment=0.88)

### 31. The evaluation of MIMIC-CXR-pretrained models on Open-I is considered appropriate for testing the generalization capability of the models due to the differing clinical properties of the datasets.

Durum: `qualified` · Soru ilgisi: `0.20`

- [1 Multi-modal Understanding and Generation for Medical](https://arxiv.org/pdf/2105.11333) — Page 6, chars 25883–25943 — “pre-trained models on Open-I is an appropriate setup to test” (entailment=0.62)

### 32. The benchmark includes 2,263 items from 13 task-specific datasets derived from de-identified cardiovascular records and examination data, reflecting real-world clinical workflows.

Durum: `qualified` · Soru ilgisi: `0.45`

- [MyoCardBench: A Real-World Data Benchmark for Evaluating Large Language Models in Clinically Authentic Cardiovascular Care Scenarios](https://arxiv.org/abs/2607.25186) — Title: MyoCardBench: A Real-World Data Benchmark for Evaluating Large Language Models in Clinically Authentic Cardiovascular Care Scenarios, chars 1385–1530 — “Methods: MyoCardBench includes 2,263 items from 13 task-specific datasets derived from de-identified cardiovascular records and examination data.” (entailment=0.95)

### 33. Encoder–decoder based multimodal integration models are designed to actively generate outputs, such as image captions or diagnostic reports, conditioned on multimodal inputs.

Durum: `qualified` · Soru ilgisi: `0.96`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Preliminary information > Model architecture > Encoder–decoder based multimodal integration, chars 30914–31080 — “In medical applications, encoder–decoder models have significant potential for automating diagnostic report generation, thereby reducing the workload of radiologists.” (entailment=0.75)

### 34. In medical applications, encoder–decoder models can automate diagnostic report generation, reducing radiologist workload and minimizing human error.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Preliminary information > Model architecture > Encoder–decoder based multimodal integration, chars 30914–31080 — “In medical applications, encoder–decoder models have significant potential for automating diagnostic report generation, thereby reducing the workload of radiologists.” (entailment=0.97)

### 35. Text-conditioned image generation in encoder–decoder models can simulate rare pathological cases, enhancing training dataset diversity for medical education and model development.

Durum: `qualified` · Soru ilgisi: `0.20`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Preliminary information > Model architecture > Encoder–decoder based multimodal integration, chars 31240–31433 — “Furthermore, text-conditioned image generation can be used to simulate rare pathological cases, thereby enhancing the diversity of training datasets for medical education and model development.” (entailment=0.93)

### 36. Vision-language models (VLMs) often produce fluent yet unjustified conclusions that are not grounded in visual evidence or contradict medical knowledge.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models](https://arxiv.org/html/2604.08815) — Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models > 1 Introduction, chars 3672–3847 — “Despite strong performance, these systems often produce fluent yet unjustified conclusions that are not grounded in visual evidence or contradict medical knowledge [ 1 , 9 ] .” (entailment=0.98)

### 37. Clinical diagnosis involves integrating heterogeneous sources of information, such as image appearance, spatial localization, statistical patterns, terminology consistency, and uncertainty awareness, and clinicians defer conclusions when these sources disagree.

Durum: `qualified` · Soru ilgisi: `0.46`

- [Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models](https://arxiv.org/html/2604.08815) — Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models > 1 Introduction, chars 4304–4478 — “Radiologists integrate heterogeneous sources of information: image appearance, spatial localization, statistical patterns, terminology consistency, and uncertainty awareness.” (entailment=0.97)

### 38. Vision-language models (VLMs) are increasingly explored for clinical decision support, including medical visual question answering, report generation, and diagnostic assistance [ 8 , 21 ] . Despite strong performance, these systems often produce fluent yet unjustified conclusions that are not grounded in visual evidence or contradict medical knowledge [ 1 , 9 ] . This phenomenon, commonly referred to as medical hallucination , remains a major barrier to safe deployment [ 24 ] , [ 11 ] . Existing evaluation protocols primarily measure answer accuracy, which fails to detect reasoning inconsistencies such as incorrect anatomical attribution or incompatible clinical relations [ 22 ] .

Durum: `qualified` · Soru ilgisi: `0.80`

- [Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models](https://arxiv.org/html/2604.08815) — Towards Responsible Multimodal Medical Reasoning via Context-Aligned Vision-Language Models > 1 Introduction, chars 3482–4171 — “Vision-language models (VLMs) are increasingly explored for clinical decision support, including medical visual question answering, report generation, and diagnostic assistance [ 8 , 21 ] . Despite strong performance, these systems often produce fluent yet unjustified conclusions that are not grounded in visual evidence or contradict medical knowledge [ 1 , 9 ] . This phenomenon, commonly referred” (entailment=0.98)

### 39. Mammo-CLIP, pre-trained on mammogram-report pairs, achieves zero-shot classification accuracy of 62.0% on RSNA for X-ray and 76.0% for CT, with 15.0% on a separate dataset, demonstrating performance in abnormality detection and image-text alignment.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based cross-modal alignment > Table 6., chars 58782–58874 — “Mammo-CLIP UPMC, VinDr X-ray, CT Report Zero-shot classification ACC 62.0, 76.0, 15.0 (RSNA)” (entailment=0.95)

### 40. BLIP, designed for medical image-text alignment, achieves i2t@1 of 36.52 and i2t@10 of 72.62 on the PubMed Image-Text dataset, indicating limited effectiveness in image-to-text retrieval for brain and other imaging modalities.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based cross-modal alignment > Table 6., chars 58992–59119 — “BLIP PubMed Image-Text Xray, CT, MRI, Microscopy, Fundus Imaging Caption Retrieval i2t@1 i2t@10 36.52 72.62 (PubMed Image-Text)” (entailment=0.85)

### 41. The literature search for multimodal vision-language models in radiology was conducted using Google Scholar and Arxiv with custom queries combining keywords related to foundation models, medical imaging, and specific tasks.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Research approach, chars 15305–15435 — “We conducted an extensive search using Google Scholar and Arxiv, utilizing the advanced search tools available on these platforms.” (entailment=0.75)

### 42. The review focuses specifically on vision-language models applied in medical imaging, analyzing recent advances in architectures, data modalities, and clinical applications with emphasis on interpretability, scalability, and domain-specific challenges.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Research approach, chars 16408–16593 — “The objective is to analyze recent advances in architectures, data modalities, and clinical applications, with emphasis on interpretability, scalability, and domain-specific challenges.” (entailment=0.90)

### 43. Only preprints demonstrating sound methodological quality and adequate experimental validation were retained, and non-English studies were excluded to ensure coherence and clarity in the synthesis of findings.

Durum: `qualified` · Soru ilgisi: `0.96`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Research approach, chars 17175–17388 — “Scientific rigor and reliability were preserved by applying a critical appraisal process, through which only preprints demonstrating sound methodological quality and adequate experimental validation were retained.” (entailment=0.92)

### 44. Contrastive learning is the most frequently used method in combined self-supervised pretraining, with some studies combining it with masked modeling or generative tasks, and one study using a pretext task before contrastive learning.

Durum: `qualified` · Soru ilgisi: `0.46`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Combined Approaches., chars 40182–40339 — “Contrastive learning emerged as the most frequent method in a combined SSL pretraining strategy, being utilized in 6 out of the 8 studies 79 – 81 , 84 – 86 .” (entailment=0.97)

### 45. One study demonstrated that a multimodal foundation model outperformed radiologists in identifying clinically significant abnormalities on X-ray images, indicating potential clinical superiority in specific tasks.

Durum: `qualified` · Soru ilgisi: `1.00`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Combined Approaches., chars 42557–42740 — “compared zero-shot AI performance against radiologists in identifying clinically significant abnormalities on X-rays, demonstrating that the AI outperformed radiologists on this task.” (entailment=0.93)

### 46. The literature search for multimodal foundation models in medical imaging was conducted using PubMed, Scopus, and Google Scholar, with search terms combining self-supervised learning, medical imaging modalities, and multimodal inputs.

Durum: `qualified` · Soru ilgisi: `1.00`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > Methods > Search Strategy, chars 66348–66444 — “We also excluded studies that only used different imaging modalities as their multimodal inputs.” (entailment=0.75)

### 47. Only studies that applied multimodal self-supervised pre-trained models to a clinically relevant downstream medical imaging task were included, excluding those that used derived imaging features or focused on image registration.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > Methods > Search Strategy, chars 66978–67124 — “Furthermore we constrained our inclusion criteria to studies that applied the multimodal SSL pretrained models to a downstream medical image task.” (entailment=0.97)

### 48. The definition of a clinically relevant task excludes downstream tasks that do not provide meaningful clinical decision support, such as classifying frame numbers in echocardiography sequences.

Durum: `qualified` · Soru ilgisi: `0.20`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > Methods > Search Strategy, chars 67331–67480 — “We defined a clinically relevant task as one that directly relates to a clinical application or has the potential to inform clinical decision-making.” (entailment=0.50)

### 49. TV-SAM improved zero-shot segmentation capabilities by integrating GPT-4-generated descriptive prompts into a text-visual-prompt segment anything model framework, achieving an average Dice score of 0.831 on the polyp benchmark across X-ray, CT, MRI, ultrasound, microscopy, and dermoscopy images.

Durum: `qualified` · Soru ilgisi: `0.46`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder–decoder based multi-modal integration > Table 8., chars 67803–67992 — “TV-SAM Private dataset attributed to company X-ray, CT, MRI, Ultrasound, Microscopy, Dermoscopy Text generated by GPT-4, Bbox generated by GLIP Segmentation Avg Dice 0.831 (Polyp benchmark)” (entailment=0.95)

### 50. SERPENT-VLM demonstrated consistent report generation performance on X-ray and CT datasets with BLEU4 and ROUGE-L scores of 0.190 and 0.326 respectively, showing reduced hallucination and robustness even with noisy or incomplete inputs.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder–decoder based multi-modal integration > Table 8., chars 67994–68091 — “SERPENT-VLM IU X-Ray, ROCO X-ray, CT Text Report generation BLEU4, ROUGE-L 0.190,0.326 (IU X-Ray)” (entailment=0.90)

### 51. BiomedCoOp achieved 86.93% accuracy and 82.74% harmonic mean in few-shot classification tasks across diverse imaging modalities including CT, dermoscopy, endoscopy, fundus imaging, and pathology slides using datasets such as CTKidney and Kvasir.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder–decoder based multi-modal integration > Table 8., chars 68093–68272 — “BiomedCoOp CTKidney, DermaMNIST, Kvasir, RETINA, LC25000 CT, Dermoscopy, Endoscopy, Fundus Imaging, Pathology Slides Text Classification ACC, Harmonic Mean 86.93, 82.74 (CTKidney)” (entailment=0.85)

### 52. Realizing the potential of multimodal Foundation Models in routine clinical practice requires navigating substantial challenges related to data, evaluation, deployment, and clinical integration.

Durum: `qualified` · Soru ilgisi: `0.63`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion > Guideline Overview., chars 52588–52875 — “While our systematic review underscores the significant advancements and immense potential of multimodal Foundation Models, realizing this potential in routine clinical practice requires navigating substantial challenges related to data, evaluation, deployment, and clinical integration.” (entailment=0.98)

### 53. Human-centered evaluation metrics are more effective than simple technical metrics for assessing the clinical utility of multimodal foundation models in radiology, as they capture clinical relevance, workflow integration, and expert reasoning.

Durum: `qualified` · Soru ilgisi: `1.00`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion, chars 51003–51250 — “was likely driven by the challenges of evaluating the clinical utility of generated reports and synthetic X-rays through simple metrics, where human-centered approaches better capture clinical relevance, workflow integration, and expert reasoning.” (entailment=0.95)

### 54. Variations in medical imaging equipment and clinical protocols across healthcare settings introduce distribution shifts that compromise the generalizability of multimodal foundation models.

Durum: `qualified` · Soru ilgisi: `0.63`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion > Guidelines for Dataset Curators., chars 62720–62908 — “Additionally, variations in, e.g., medical imaging equipment and protocols across different healthcare settings can introduce distribution shifts, further impacting model generalizability.” (entailment=0.95)

### 55. Dataset curators should prioritize diversity in patient demographics, imaging equipment, and clinical protocols to improve model fairness and generalizability across different healthcare environments.

Durum: `qualified` · Soru ilgisi: `0.46`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion > Guidelines for Dataset Curators., chars 62909–63103 — “To mitigate these biases, dataset curators should prioritize diversity in patient demographics, imaging equipment, and clinical protocols, accounting for variations in healthcare infrastructure.” (entailment=0.92)

### 56. Including metadata such as patient demographics, imaging devices, and scanning protocols is essential for assessing model fairness and generalizability across subgroups and clinical settings.

Durum: `qualified` · Soru ilgisi: `0.46`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion > Guidelines for Dataset Curators., chars 63104–63335 — “Additionally, they should include metadata – such as patient demographics, imaging devices, and scanning protocols – to enable model developers to assess fairness and generalizability across diverse subgroups and clinical settings.” (entailment=0.90)

### 57. Encoder-based cross-modal alignment models such as MAVL, DeViDe, and IMITATE demonstrate strong performance in X-ray image classification and segmentation tasks using datasets like MIMIC-CXR and ChestX-ray14.

Durum: `qualified` · Soru ilgisi: `0.63`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Specific domain transfer applications > X-ray imaging > Table 1., chars 33126–33209 — “Encoder based cross-modal alignment MAVL MIMIC-CXR v2 Text Zero-shot classification” (entailment=0.88)

### 58. Models employing encoder–decoder architectures, such as RoentGen and ConTEXTual Net, show improved performance in generating radiology reports and segmenting chest radiographs by integrating textual context with visual data.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Specific domain transfer applications > X-ray imaging > Table 1., chars 37009–37175 — “[ 40 ] developed ConTEXTual Net, a multi-modal vision-language foundation model that integrates radiology reports into the segmentation process for chest radiographs.” (entailment=0.92)

### 59. Libra, a temporally aware multi-modal LLM, achieves strong performance in radiology report generation with BLEU scores of 51.3 and 24.5 on MIMIC-CXR and MIMIC-Ext-MIMIC-CXR-VQA datasets, indicating potential for dynamic clinical reasoning.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Specific domain transfer applications > X-ray imaging > Table 1., chars 37009–37175 — “[ 40 ] developed ConTEXTual Net, a multi-modal vision-language foundation model that integrates radiology reports into the segmentation process for chest radiographs.” (entailment=0.50)

### 60. Bias in vision-language models for medical imaging arises from training datasets that do not adequately represent diverse populations, leading to imbalanced model performance across racial, ethnic, socioeconomic, and linguistic groups.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Discussion > Bias and variance in VLMs, chars 77884–78040 — “Bias arises from training datasets that do not adequately represent diverse populations, leading to an imbalanced model performance across different groups.” (entailment=0.98)

### 61. The dominance of English in medical VLM training datasets introduces significant community bias, particularly disadvantaging non-English speakers and limiting the real-world applicability of monolingual models in global healthcare settings.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Discussion > Bias and variance in VLMs, chars 78570–78738 — “This dominance restricts the performance of monolingual VLMs in multilingual tasks and introduces community bias, which disproportionately affects non-English speakers.” (entailment=0.97)

### 62. Recent datasets such as FairCLIP, PadChest, PMC-15 M, and Mammo-CLIP have been developed to include racially and demographically diverse data, with some models like PadChest incorporating non-English languages to improve cross-lingual performance.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Discussion > Bias and variance in VLMs, chars 78992–79180 — “For example, datasets such as FairCLIP [ 54 ], PadChest [ 98 ], PMC-15 M [ 75 ], and Mammo-CLIP [ 68 ] include racially and demographically diverse data to reduce bias and ensure fairness.” (entailment=0.92)

### 63. Publicly accessible medical datasets are limited in scale compared to the internet-scale data used to train general domain Foundation Models, creating a significant hurdle in the development of multimodal medical AI models.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion, chars 47344–47501 — “The largest publicly accessible medical datasets 92 , 111 – 113 pale in comparison to the internet-scale data used to train general domain Foundation Models.” (entailment=0.98)

### 64. Multimodal Foundation Models that integrate diverse patient data—such as genetic, clinical, ICD codes, speech, and patient size profiles—offer a more comprehensive view of the patient, aligning with physician clinical practice and enabling discovery of complex patient data relationships.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion, chars 49177–49349 — “The inclusion of these diverse modalities provides the model with a more comprehensive view of the patient, mirroring the approach taken by physicians in clinical practice.” (entailment=0.97)

### 65. Standard quantitative metrics are insufficient for evaluating the clinical utility of generated radiology reports and synthetic X-rays, and human-centered metrics—such as human preference and performance evaluations—are more effective at capturing clinical relevance and expert reasoning.

Durum: `qualified` · Soru ilgisi: `1.00`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 3. Discussion, chars 50224–50341 — “Standard quantitative metrics may not capture clinical nuances, leading some studies to adopt human-centered metrics.” (entailment=0.88)

### 66. Llama3-Med, a vision-language foundation model, demonstrates strong performance in generating diagnostic reports and supporting clinical decisions across X-ray, CT, MRI, and ultrasound imaging modalities.

Durum: `qualified` · Soru ilgisi: `1.00`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based multi-modal attention > Table 7., chars 63467–63567 — “Llama3-Med Claude 3 Opu, LLaMA 3 70B X-ray, CT, MRI, Ultrasound, PET Text VQA Recall 31.20 (VQA-RAD)” (entailment=0.88)

### 67. PPE, a prior prompt encoder model, achieves high segmentation performance on X-rays, CT scans, and MRIs using text-guided prompts, with Dice and mIoU scores of 80.59 and 67.59 on MoNuSeg, respectively.

Durum: `qualified` · Soru ilgisi: `0.20`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based multi-modal attention > Table 7., chars 63627–63738 — “Text generated by BLIP, Hand-craft, Mask label generated by LViT Segmentation Dice, mIoU 80.59, 67.59 (MoNuSeg)” (entailment=0.50)

### 68. LLaVA-Med, trained using GPT-4-generated instruction data, achieves a recall of 64.75 on the VQA-RAD dataset for X-ray, CT, MRI, and ultrasound imaging, indicating moderate performance in visual-linguistic reasoning tasks.

Durum: `qualified` · Soru ilgisi: `0.80`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based multi-modal attention > Table 7., chars 63740–63841 — “LLaVA-Med PMC-15 M X-ray, CT, MRI, Ultrasound, PET Text generated by GPT-4 VQA Recall 64.75 (VQA-RAD)” (entailment=0.85)

### 69. TFA-LT, a text-guided framework for long-tailed medical image classification, achieves 70.48 accuracy on ISIC2018 for dermoscopy and fundus imaging, suggesting limited generalizability across diverse imaging modalities.

Durum: `qualified` · Soru ilgisi: `0.20`

- [Vision-language foundation models for medical imaging: a review of current practices and innovations - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411343) — Contributed equally. > Foundation models in medical imaging > Multi-domain integrated applications > Encoder based multi-modal attention > Table 7., chars 63843–63937 — “TFA-LT ISIC2018, APTOS2019 Dermoscopy, Fundus Imaging Text Classification ACC 70.48 (ISIC2018)” (entailment=0.80)

### 70. All generative papers used X-ray images as their imaging modality and radiology reports for their corresponding modality.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative Models., chars 34285–34406 — “All generative papers used X-ray images as their imaging modality and radiology reports for their corresponding modality.” (entailment=0.99)

### 71. Four out of the seven generative studies pretrained their models by generating the findings section for radiology reports, with an average improvement of 0.002 AUROC and 0.053 F1 score over single-modality models.

Durum: `qualified` · Soru ilgisi: `0.96`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative Models., chars 34407–34533 — “Four out of the 7 papers pretrained their models based on generating the findings section for radiology reports 35 , 62 – 64 .” (entailment=0.98)

### 72. Two of the seven generative studies included human evaluation of model outputs, with radiologists assessing generated X-rays for realism and prompt coherence, finding that while the images aligned well with prompts, they could still be identified as synthetic.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative Models., chars 35845–36061 — “65 had radiologists evaluate generated X-rays for realism and prompt coherence, finding that while RoentGen demonstrated strong alignment with input prompts, radiologists could still identify the images as synthetic.” (entailment=0.96)

### 73. Three studies pretrained models by generating synthetic chest X-rays based on radiology reports or text prompts, with Chambon et al. demonstrating a 5% improvement in classifier performance when trained on synthetic and real images combined.

Durum: `qualified` · Soru ilgisi: `0.80`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative Models., chars 34920–35057 — “The remaining 3 studies pretrained their models by generating synthetic chest X-rays based on radiology reports or text prompts 65 – 67 .” (entailment=0.97)

### 74. Ten out of 48 studies leveraged existing text-based Foundation Models (LLMs) to develop Vision-Language Models (VLMs), with five focusing specifically on X-ray imaging and five capable of analyzing multiple imaging modalities.

Durum: `qualified` · Soru ilgisi: `0.96`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative VLM., chars 36260–36373 — “Ten out of 48 studies 68 – 77 leveraged existing text-based Foundation Models (LLMs) to develop VLMs ( Table 1 ).” (entailment=0.98)

### 75. Among the studies using text-based foundation models, three explored creative methods to source corresponding text, including PubMed image captions and text from medical publications and textbooks.

Durum: `qualified` · Soru ilgisi: `0.63`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative VLM., chars 36739–36896 — “Three studies found creative ways to source corresponding text, including PubMed image captions 69 and text from publications and medical textbooks 70 , 75 .” (entailment=0.95)

### 76. The model MAIRA-2 generated reports with 91% of sentences acceptable as-is, indicating minimal need for correction and suggesting potential efficiency gains for radiologists.

Durum: `qualified` · Soru ilgisi: `0.63`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative VLM., chars 39594–39782 — “77 showed that MAIRA-2 produced draft reports requiring minimal corrections, with 91% of generated sentences being acceptable as-is, suggesting potential efficiency gains for radiologists.” (entailment=0.92)

### 77. Human validation was employed in nine of the ten studies using text-based foundation models, with evaluations ranging from direct comparison to human performance to preference and performance assessments.

Durum: `qualified` · Soru ilgisi: `0.96`

- [A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12060978) — A Systematic Review and Implementation Guidelines of Multimodal Foundation Models in Medical Imaging > 2. Results > None of the studies employed human validation. > Generative VLM., chars 36260–36373 — “Ten out of 48 studies 68 – 77 leveraged existing text-based Foundation Models (LLMs) to develop VLMs ( Table 1 ).” (entailment=0.97)

## Ek C — Kaynak bazlı literatür dökümü

Araştırmada korunan **37** kaynağın tamamı, her kaynağın rolü ve çıkarılan bulgularıyla `15_literature_inventory.md` dosyasında listelenmiştir.
