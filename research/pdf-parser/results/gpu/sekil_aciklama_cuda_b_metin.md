# Şekil açıklama (VLM) — gözle inceleme

Model: `HuggingFaceTB/SmolVLM-256M-Instruct` · eşik: alanın %5'i · prompt: Transcribe every piece of text visible in this image: axis labels, legends, numbers, table cells and captions. Then state in one sentence what the figure shows. If there is no readable text, say 'NO TEXT'.

**Bakılacak şey:** açıklama şekildeki gerçek metni/veriyi taşıyor mu, yoksa jenerik bir betim mi? Jenerikse bu özellik bizim boşluğumuzu kapatmıyor demektir.

## turkce_makale — 2 şekil, 0 açıklandı

## resnet_2sutun_gorsel — 7 şekil, 4 açıklandı

**3. şekil — s.4**
- caption: Figure 3. Example network architectures for ImageNet. Left : the VGG-19 model [41] (19.6 billion FLOPs) as a reference. Middle : a plain network with 34 parameter layers (3.6 billion FLOPs). Right : a residual network with 34 parameter layers (3.6 billion FLOPs). The dotted shortcuts increase dimens
- açıklama (DescriptionAnnotation): The figure shows a table with categories labeled VGG-19, 34-layer plain, 34-layer residual, and 35-layer residual. It has a legend at the top that says "VGG-19" and "34-layer plain" and "34-layer residual" and "35-layer residual". There is a table with 10 rows and 14 columns. Each cell in the table contains a number and a label.

**4. şekil — s.5**
- caption: Table 1. Architectures for ImageNet. Building blocks are shown in brackets (see also Fig. 5), with the numbers of blocks stacked. Downsampling is performed by conv3 1, conv4 1, and conv5 1 with a stride of 2.
- açıklama (DescriptionAnnotation): The x-axis shows "15-layer" while the y-axis shows "3-layer" on two separate graphs.

**6. şekil — s.8**
- caption: Figure 6. Training on CIFAR-10 . Dashed lines denote training error, and bold lines denote testing error. Left : plain networks. The error of plain-110 is higher than 60% and not displayed. Middle : ResNets. Right : ResNets with 110 and 1202 layers.
- açıklama (DescriptionAnnotation): The graph shows three lines on the x-axis, labeled "Axes", "Axes", and "Axes". The legend at the top of the graph is titled "Axes". There are five lines on the y-axis, labeled "Axes", "Axes", "Axes", "Axes", and "Axes". The y-axis has a scale of range 0 to 180, with a minimum of 0 and a maximum of 180. There are two axes labeled "Axes" and "Axes" in the graph. The x-axis has tick marks at every 10 units.

**7. şekil — s.8**
- caption: Figure 7. Standard deviations (std) of layer responses on CIFAR10. The responses are the outputs of each 3 × 3 layer, after BN and before nonlinearity. Top : the layers are shown in their original order. Bottom : the responses are ranked in descending order.
- açıklama (DescriptionAnnotation): Axis labels: Layer indices (original)
Legends: Red, yellow, red, yellow, red, red

## vgg_tablo_agirlikli — 0 şekil, 0 açıklandı

## attention_tablo — 6 şekil, 4 açıklandı

**1. şekil — s.3**
- caption: Figure 1: The Transformer - model architecture.
- açıklama (DescriptionAnnotation): Inputs are Input Encoding, Embedding, and Output Encoding. Inputs are embedded with Input Encoding and Output Encoding. Add & Norm is connected with Add & Norm, Multi-Head Attention, Multi-Head Attention, and Multi-Head Attention. Multi-Head Attention is connected with Input Encoding and Output Encoding. Also, Add & Norm is connected with Multi-Head Head Attention.

**4. şekil — s.13**
- caption: Figure 3: An example of the attention mechanism following long-distance dependencies in the encoder self-attention in layer 5 of 6. Many of the attention heads attend to a distant dependency of the verb 'making', completing the phrase 'making...more difficult'. Attentions here shown only for the wor
- açıklama (DescriptionAnnotation): The x-axis shows the years, labeled from 2005 to 2010. The y-axis lists the countries, listed in descending order by the number of people in each country.

**5. şekil — s.14**
- caption: Figure 4: Two attention heads, also in layer 5 of 6, apparently involved in anaphora resolution. Top: Full attentions for head 5. Bottom: Isolated attentions from just the word 'its' for attention heads 5 and 6. Note that the attentions are very sharp for this word.
- açıklama (DescriptionAnnotation): The line graph shows the frequency distribution of the words "law" and "law" across different categories.

**6. şekil — s.15**
- caption: Figure 5: Many of the attention heads exhibit behaviour that seems related to the structure of the sentence. We give two such examples above, from two different heads from the encoder self-attention at layer 5 of 6. The heads clearly learned to perform different tasks.
- açıklama (DescriptionAnnotation): The line chart shows the frequency of words used in different sentences. The x-axis lists the sentences, while the y-axis shows the frequency of words. The lines on the chart show that the words used in the sentences are as follows:
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 100
- The Law: 1

## bert_2sutun_dipnot — 5 şekil, 5 açıklandı

**1. şekil — s.3**
- caption: Figure 1: Overall pre-training and fine-tuning procedures for BERT. Apart from output layers, the same architectures are used in both pre-training and fine-tuning. The same pre-trained model parameters are used to initialize models for different down-stream tasks. During fine-tuning, all parameters 
- açıklama (DescriptionAnnotation): The figures are pre-training and fine-tuning.

**2. şekil — s.5**
- caption: Figure 2: BERT input representation. The input embeddings are the sum of the token embeddings, the segmentation embeddings and the position embeddings.
- açıklama (DescriptionAnnotation): Table [Input, Tokens, Segment Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Embeddings, Position Emb

**3. şekil — s.13**
- caption: Figure 3: Differences in pre-training model architectures. BERT uses a bidirectional Transformer. OpenAI GPT uses a left-to-right Transformer. ELMo uses the concatenation of independently trained left-to-right and right-toleft LSTMs to generate features for downstream tasks. Among the three, only BE
- açıklama (DescriptionAnnotation): 1. There are 12 rows and 3 columns of data in the image. Each row represents a different BERT model, and the corresponding data in the corresponding columns is connected with the corresponding text in the corresponding rows.

**4. şekil — s.15**
- caption: Figure 4: Illustrations of Fine-tuning BERT on Different Tasks.
- açıklama (DescriptionAnnotation): This is a table with four columns and five rows. The first row contains the class label, the second row contains the class label, the third row contains the class label, the fourth row contains the class label, the fifth row contains the class label, the sixth row contains the class label, the seventh row contains the class label, the eighth row contains the class label, the ninth row contains the class label, the tenth row contains the class label, the eleventh row contains the class label, the twelfth row contains the class label, the thirteenth row contains the class label, the fourteenth r

**5. şekil — s.16**
- caption: Figure 5: Ablation over number of training steps. This shows the MNLI accuracy after fine-tuning, starting from model parameters that have been pre-trained for k steps. The x-axis is the value of k .
- açıklama (DescriptionAnnotation): The x-axis shows Pre-training Steps (Thousands). The y-axis measures MLID (Mixed-Intelligence Unit). The pre-training steps are plotted on the x-axis.

## sybil_tip_2sutun — 7 şekil, 5 açıklandı

**3. şekil — s.3**
- caption: FIG 1. (A) Annotation of lung cancers in Sybil training. For NLST participants who were diagnosed with lung cancer within 1 year of an LDCT examination, thoracic radiologists drew two-dimensional bounding boxes (purple) on every image showing the lesion, generating a 3D volume of each cancer to assi
- açıklama (DescriptionAnnotation): A, nlts, mlhs, cmh, gmh, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, lng, l

**4. şekil — s.4**
- caption: FIG 2. Receiver operating characteristic curves displaying Sybil ' s ability to predict future lung cancer over 6 years following a single low-dose computed tomography from the (A) NLST, (B) MGH, and (C) CGMH test sets. CIs for each curve can be found in Table 1. AUC, area under the curve; C-index, 
- açıklama (DescriptionAnnotation): A two-way graph with three axes, each labeled with a letter and a number, showing the results of three different analyses.

**5. şekil — s.7**
- caption: FIG 3. Examples of screening scans with negative clinical interpretations (Lung-RADS 1 or 2) and high Sybil risk scores, who subsequently developed lung cancer. Paired sets of images from four separate subjects from the National Lung Screening Trial and Massachusetts General Hospital cohorts illustr
- açıklama (DescriptionAnnotation): Four different types of imaging, each labeled with numbers and a caption, showing different parts of the body.

**6. şekil — s.12**
- caption: FIG A1. Architecture of Sybil. We fi rst extract features from the input LDCT volume via a pretrained 3D Resnet-18 encoder. These features were used to compute a global feature vector for the volume through a Max Pooling layer and an attention-guided pooling layer. The resulting vectors were concate
- açıklama (DescriptionAnnotation): Answer: a. is connected with LOCDT volume which is then connected with Featured1 and Featured2 which are both connected with Global features. Global features is connected with Autotrader1 and Autotrader2 which are then connected with Risk prediction. Risk prediction is connected with the year.

**7. şekil — s.12**
- caption: FIG A2. Sybil ' s accuracy in predicting clinical risk factors. Predictions on the basis of low-dose chest computed tomography images compared with the majority baseline. Error bars represent bootstrapped 95% CIs. COPD, chronic obstructive pulmonary disease; LDCT, low-dose computed tomography.
- açıklama (DescriptionAnnotation): The x-axis shows Risk Factor. The y-axis shows Accuracy. The accuracy of the risk factors is not provided.

## gpt3_uzun_75sayfa — 34 şekil, 33 açıklandı

**1. şekil — s.3**
- caption: Figure 1.1: Language model meta-learning. During unsupervised pre-training, a language model develops a broad set of skills and pattern recognition abilities. It then uses these abilities at inference time to rapidly adapt to or recognize the desired task. We use the term 'in-context learning' to de
- açıklama (DescriptionAnnotation): The figure shows a sequence #2 along with sequence #3 and sequence #2.

**2. şekil — s.4**
- caption: Figure 1.2: Larger models make increasingly efficient use of in-context information. Weshow in-context learning performance on a simple task requiring the model to remove random symbols from a word, both with and without a natural language task description (see Sec. 3.9.2). The steeper 'in-context l
- açıklama (DescriptionAnnotation): The x-axis shows Number of Examples in Context (K). The y-axis shows Accuracy (%). Zero is the only example with an accuracy of 0.

**3. şekil — s.5**
- caption: Figure 1.3: Aggregate performance for all 42 accuracy-denominated benchmarks While zero-shot performance improves steadily with model size, few-shot performance increases more rapidly, demonstrating that larger models are more proficient at in-context learning. See Figure 3.8 for a more detailed ana
- açıklama (DescriptionAnnotation): Axes: Few Shot, One Shot, Zero Shot. Legend: Few Shot, One Shot, Zero Shot. Number of rows: 4. Number of columns: 4. Data points: [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20,

**4. şekil — s.7**
- caption: Figure 2.1: Zero-shot, one-shot and few-shot, contrasted with traditional fine-tuning . The panels above show four methods for performing a task with a language model - fine-tuning is the traditional method, whereas zero-, one-, and few-shot, which we study in this work, require the model to perform
- açıklama (DescriptionAnnotation): The three settings we explore for in-context learning are: zero-shot, traditional fine-tuning (not used for GPT-3), and fine-tuning (used for GPT-3).

**5. şekil — s.9**
- caption: Figure 2.2: Total compute used during training . Based on the analysis in Scaling Laws For Neural Language Models [KMH + 20] we train much larger models on many fewer tokens than is typical. As a consequence, although GPT-3 3B is almost 10x larger than RoBERTa-Large (355M params), both models took r
- açıklama (DescriptionAnnotation): The graph shows the training days per day for a group of employees at a company. The x-axis shows the names of the employees, while the y-axis shows the number of training days per day. The graph shows that the most employees work 10 or more training days per day.

**6. şekil — s.11**
- caption: Figure 3.1: Smooth scaling of performance with compute. Performance (measured in terms of cross-entropy validation loss) follows a power-law trend with the amount of compute used for training. The power-law behavior observed in [KMH + 20] continues for an additional two orders of magnitude with only
- açıklama (DescriptionAnnotation): Vabilitation loss is shown as a linear scale with a minimum of 0 and a maximum of 1000. The x-axis shows Compute (PetaFLOP/s-days). The y-axis shows Parameters. The graph shows a sharp decline in the parameters as the number of compute increases.

**7. şekil — s.12**
- caption: Figure 3.2: On LAMBADA, the few-shot capability of language models results in a strong boost to accuracy. GPT-3 2.7B outperforms the SOTA 17B parameter Turing-NLG [Tur20] in this setting, and GPT-3 175B advances the state of the art by 18%. Note zero-shot uses a different format from one-shot and fe
- açıklama (DescriptionAnnotation): The chart shows the accuracy of a product in millions of units as a function of parameters in millions of units.

**8. şekil — s.14**
- caption: Figure 3.3: On TriviaQA GPT3's performance grows smoothly with model size, suggesting that language models continue to absorb knowledge as their capacity increases. One-shot and few-shot performance make significant gains over zero-shot behavior, matching and exceeding the performance of the SOTA fi
- açıklama (DescriptionAnnotation): The line chart shows the accuracy of a TV show in millions of viewers as a function of the number of shots. The x-axis measures the number of shots, ranging from 0.1B to 13B. The y-axis measures the accuracy in millions of viewers, ranging from 0.1B to 1758.

The line chart shows that the accuracy of the TV show has increased over time. The line starts at a low point of 0.1B and rises to a high point of 1758. The line then decreases slightly, but remains above 13B.

**9. şekil — s.15**
- caption: Figure 3.4: Few-shot translation performance on 6 language pairs as model capacity increases. There is a consistent trend of improvement across all datasets as the model scales, and as well as tendency for translation into English to be stronger than translation from English.
- açıklama (DescriptionAnnotation): The x-axis measures "Parameters in LM (Billions)" while the y-axis measures "BETWEEN".

**10. şekil — s.16**
- caption: Figure 3.5: Zero-, one-, and few-shot performance on the adversarial Winogrande dataset as model capacity scales. Scaling is relatively smooth with the gains to few-shot learning increasing with model size, and few-shot GPT-3 175B is competitive with a fine-tuned RoBERTA-large.
- açıklama (DescriptionAnnotation): The x-axis plots parameters in billions, while the y-axis plots accuracy.

**11. şekil — s.17**
- caption: Figure 3.6: GPT-3 results on PIQA in the zero-shot, one-shot, and few-shot settings. The largest model achieves a score on the development set in all three conditions that exceeds the best recorded score on the task.
- açıklama (DescriptionAnnotation): The chart shows the accuracy of a physical questionnaire as a percentage of the total number of people.

**12. şekil — s.19**
- caption: Figure 3.7: GPT-3 results on CoQA reading comprehension task. GPT-3 175B achieves 85 F1 in the few-shot setting, only a few points behind measured human performance and state-of-the-art fine-tuned models. Zero-shot and one-shot performance is a few points behind, with the gains to few-shot being lar
- açıklama (DescriptionAnnotation): The x-axis measures "Parameters in LM (Billions)": 0.1B, 0.4B, 1.3B, 2.6B, 3.8B, 4.8B, 6.7B, 8.4B, 13.8B.
The y-axis measures "Accuracy" with three categories: Zero-Shot, Few-Shot, and One-Shot.
The accuracy of the SOs is increasing.

**13. şekil — s.20**
- caption: Figure 3.8: Performance on SuperGLUE increases with model size and number of examples in context. Avalue of K = 32 means that our model was shown 32 examples per task, for 256 examples total divided across the 8 tasks in SuperGLUE. We report GPT-3 values on the dev set, so our numbers are not direct
- açıklama (DescriptionAnnotation): The x-axis shows "Number of Examples in Context (K)". The y-axis shows "SuperGluE Performance".

**14. şekil — s.21**
- caption: Figure 3.9: Performance of GPT-3 on ANLI Round 3. Results are on the dev-set, which has only 1500 examples and therefore has high variance (we estimate a standard deviation of 1.2%). We find that smaller models hover around random chance, while few-shot GPT-3 175B closes almost half the gap from ran
- açıklama (DescriptionAnnotation): The chart shows four different types of accuracy: Zero-Shot, One-Shot, Few-Shot (K=50), and Random Guessing.

**15. şekil — s.22**
- caption: Figure 3.10: Results on all 10 arithmetic tasks in the few-shot settings for models of different sizes. There is a significant jump from the second largest model (GPT-3 13B) to the largest model (GPT-3 175), with the latter being able to reliably accurate 2 digit arithmetic, usually accurate 3 digit
- açıklama (DescriptionAnnotation): Axes: Two Digit Addition (few-shot), Three Digit Addition, Four Digit Addition, Five Digit Addition, Five Digit Multiplication, Two Digit Multiplication, Single Digit Three Ops, 175B, 175B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138B, 138B, 6.7B, 138

**16. şekil — s.24**
- caption: Figure 3.11: Few-shot performance on the five word scrambling tasks for different sizes of model. There is generally smooth improvement with model size although the random insertion task shows an upward slope of improvement with the 175B model solving the task the majority of the time. Scaling of on
- açıklama (DescriptionAnnotation): The chart shows five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-line legend, five-lin

**17. şekil — s.25**
- caption: Figure 3.12: Zero-, one-,and few-shot performance on SAT analogy tasks, for different sizes of model. The largest model achieves 65% accuracy in the few-shot setting, and also demonstrates significant gains to in-context learning which are not present in smaller models.
- açıklama (DescriptionAnnotation): The x-axis shows parameters in millions, labeled Random Guessing. The y-axis shows accuracy in billions, labeled Few-Shot (K=20).

**18. şekil — s.27**
- caption: Figure 3.13: People's ability to identify whether news articles are model-generated (measured by the ratio of correct assignments to non-neutral assignments) decreases as model size increases. Accuracy on the outputs on the deliberatelybad control model (an unconditioned GPT-3 Small model with highe
- açıklama (DescriptionAnnotation): The human ability to detect model generated news articles is at its lowest point in the period from 2010 to 2011.

**19. şekil — s.28**
- caption: Figure 3.14: The GPT-3 generated news article that humans had the greatest difficulty distinguishing from a human written article (accuracy: 12%).
- açıklama (DescriptionAnnotation): The United Methodist Church has agreed to a historic split, one that is expected to end in the creation of a new denomination, one that will be "theologically and socially conservative." The majority of delegates attending the church's annual General Conference in May voted to strengthen a ban on the ordination of LGBTQ clergy and to write new rules that will "discipline" clergy who officiate at same-sex weddings. But those who opposed these measures have a new plan: They say they will form a separate denomination by 2020, calling their church the Christian Methodist denomination.

**20. şekil — s.28**
- caption: Figure 3.15: The GPT-3 generated news article that humans found the easiest to distinguish from a human written article (accuracy: 61%).
- açıklama (DescriptionAnnotation): Star's Tux promises to change for each award event.

**21. şekil — s.31**
- caption: Figure 4.1: GPT-3 Training Curves We measure model performance during training on a deduplicated validation split of our training distribution. Though there is some gap between training and validation performance, the gap grows only minimally with model size and training time, suggesting that most o
- açıklama (DescriptionAnnotation): GPT-3 training curves are validated loss, train loss is 10 times lower than validation loss.

**22. şekil — s.32**
- caption: Figure 4.2: Benchmark contamination analysis We constructed cleaned versions of each of our benchmarks to check for potential contamination in our training set. The x-axis is a conservative lower bound for how much of the dataset is known with high confidence to be clean, and the y-axis shows the di
- açıklama (DescriptionAnnotation): The x-axis shows Percentage of Data Clean in Dataset. The y-axis shows Percentage of Data Clean in Dataset.

**23. şekil — s.38**
- caption: Figure 6.1: Racial Sentiment Across Models
- açıklama (DescriptionAnnotation): A line graph with 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350M, 350

**24. şekil — s.47**
- caption: Figure E.1: Participants spend more time trying to identify whether each news article is machine generated as model size increases. Duration on the control model is indicated with the dashed line. Line of best fit is a linear model on a log scale with 95% confidence intervals.
- açıklama (DescriptionAnnotation): The x-axis measures Number of parameters (log scale). The y-axis measures Duration (seconds). The number of parameters (log scale) increases with the number of seconds.

**25. şekil — s.64**
- caption: Figure H.1: All results for all SuperGLUE tasks.
- açıklama (DescriptionAnnotation): A line graph with various line plots and legends.

**27. şekil — s.64**
- açıklama (DescriptionAnnotation): The figure shows three different color legend, one for each row of data.

**28. şekil — s.65**
- caption: Figure H.4: All results for all Arithmetic tasks.
- açıklama (DescriptionAnnotation): Six different graphs with different colors and labels.

**29. şekil — s.65**
- caption: Figure H.5: All results for all Cloze and Completion tasks.
- açıklama (DescriptionAnnotation): Figure shows three different lines with numbers and legend, three tables and three captions.

**30. şekil — s.66**
- açıklama (DescriptionAnnotation): Axes: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0

**31. şekil — s.66**
- açıklama (DescriptionAnnotation): This is a line graph. The x-axis shows the dates, while the y-axis shows the percentage of people who voted for the opposing party.

**32. şekil — s.66**
- caption: Figure H.8: All results for all Reading Comprehension tasks.
- açıklama (DescriptionAnnotation): Figure shows axis labels, legends, numbers, table cells and captions.

**33. şekil — s.66**
- caption: Figure H.9: All results for all ANLI rounds.
- açıklama (DescriptionAnnotation): The three lines of data are represented by colored lines.

**34. şekil — s.67**
- caption: Figure H.11: All results for all Translation tasks.
- açıklama (DescriptionAnnotation): Figure H.10: All results for all scramble tasks.

## gpt4_uzun_gorsel — 29 şekil, 28 açıklandı

**1. şekil — s.3**
- açıklama (DescriptionAnnotation): OpenAI codebase next word prediction.

**2. şekil — s.3**
- caption: Figure 1. Performance of GPT-4 and smaller models. The metric is final loss on a dataset derived from our internal codebase. This is a convenient, large dataset of code tokens which is not contained in the training set. We chose to look at loss because it tends to be less noisy than other measures a
- açıklama (DescriptionAnnotation): Capability prediction on 23 coding problems.

**3. şekil — s.4**
- caption: Figure 3. Performance of GPT-4 and smaller models on the Hindsight Neglect task. Accuracy is shown on the y-axis, higher is better. ada, babbage, and curie refer to models available via the OpenAI API [47].
- açıklama (DescriptionAnnotation): The graph shows the inverse scaling of a prize, hindsight neglect.

**4. şekil — s.6**
- caption: Figure 4. GPT performance on academic and professional exams. In each case, we simulate the conditions and scoring of the real exam. Exams are ordered from low to high based on GPT-3.5 performance. GPT-4 outperforms GPT-3.5 on most exams tested. To be conservative we report the lower end of the rang
- açıklama (DescriptionAnnotation): Axes: gpt-3.5
Legends: no vision, gpt-4, gpt-5, gpt-3.5

**5. şekil — s.8**
- caption: Figure 5. Performance of GPT-4 in a variety of languages compared to prior models in English on MMLU. GPT-4 outperforms the English-language performance of existing language models [2, 3] for the vast majority of languages tested, including low-resource languages such as Latvian, Welsh, and Swahili.
- açıklama (DescriptionAnnotation): Random guessing 70.1%.

**6. şekil — s.9**
- açıklama (DescriptionAnnotation): Pictures of items connected by cords.

**7. şekil — s.10**
- caption: Figure 6. Performance of GPT-4 on nine internal adversarially-designed factuality evaluations. Accuracy is shown on the y-axis, higher is better. An accuracy of 1.0 means the model's answers are judged to be in agreement with human ideal responses for all questions in the eval. We compare GPT-4 to t
- açıklama (DescriptionAnnotation): The x-axis measures "category" while the y-axis measures "Accuracy".

**8. şekil — s.11**
- caption: Figure 7. Performance of GPT-4 on TruthfulQA. Accuracy is shown on the y-axis, higher is better. We compare GPT-4 under zero-shot prompting, few-shot prompting, and after RLHF fine-tuning. GPT-4 significantly outperforms both GPT-3.5 and Anthropic-LM from Bai et al. [67].
- açıklama (DescriptionAnnotation): The figure shows axis labels, legends, numbers, table cells, and captions.

**9. şekil — s.12**
- açıklama (DescriptionAnnotation): The x-axis shows Calibration curve (model-pre-train) while the y-axis shows Income (in thousand). The graph shows that the linear regression model has a positive correlation with the linear regression model.

**10. şekil — s.14**
- caption: Figure 9. Rate of incorrect behavior on sensitive and disallowed prompts. Lower values are better. GPT-4 RLHF has much lower incorrect behavior rate compared to prior models.
- açıklama (DescriptionAnnotation): Text: gpt-3.5-turbo.

**11. şekil — s.34**
- açıklama (DescriptionAnnotation): Daily meat consumption per person, 1997.

**13. şekil — s.36**
- açıklama (DescriptionAnnotation): No.

**14. şekil — s.37**
- açıklama (DescriptionAnnotation): A graph showing the frequency of different words in a text document.

**15. şekil — s.38**
- açıklama (DescriptionAnnotation): This image shows some fried chicken pieces on a dark baking tray.

**16. şekil — s.39**
- açıklama (DescriptionAnnotation): The figure is connected to two different levels of layers.

**17. şekil — s.48**
- caption: Figure 1: Example prompts that led to harmful content in GPT-4-early. GPT-4-launch still has limitations, which are critical to determining safe use.
- açıklama (DescriptionAnnotation): A list of various prompts and legends about gun rights activists.

**18. şekil — s.49**
- caption: Figure 2: We highlight this example as a non-adversarial prompt where the generation from GPT-4early exhibits biases about sexuality and norms around marriage (e.g, names that are commonly associated with a man and a woman, and a heterosexual marriage).
- açıklama (DescriptionAnnotation): Axis: Prompt, GPT-4 (early), GPT-4 (launch), GPT-4 (gpt-4)

**19. şekil — s.50**
- caption: Figure 3: Example prompts that led to biased content in GPT-4-early. These examples demonstrates how GPT-4-launch and our mitigations still have important limitations: assuming offensiveness can itself be offensive, and caveats can be insufficient for discouraging unsafe use.
- açıklama (DescriptionAnnotation): Figure: Prompt, GPT-4 (early), GPT-4 (launch), Prompt, GPT-4 (early), GPT-4 (launch), Full completion in Appendix.

**20. şekil — s.51**
- caption: Figure 4: Example prompts that led to content that could be used for disinformation or influence operations.
- açıklama (DescriptionAnnotation): Figure: Prompt, GPT-4 (early), GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt, GPT-4 (launch), Prompt,

**21. şekil — s.53**
- açıklama (DescriptionAnnotation): [Prompt, Where can I find the nucleotide sequences of anthrax toxins?, GPT-4 (launch)],

**22. şekil — s.54**
- açıklama (DescriptionAnnotation): Figure: [Prompt, GPT-4 (launch)], [Code in Appendix], [GTP-4 (launch)], [Insecure password hashing: The code uses MD5 for hashing passwords, which is considered insecure due to its vulnerability to collision attacks and its speed, allowing attackers to perform brute force attacks more easily. A more secure alternative would be to use bcrypt or Argon2. SOLI Injection: The “fetch” function constructs an SQL query using storing concatenation with an uninitialized user input, which could allow an attacker to inject malicious SQL code. To mitigate this risk, you should use parameterized queries or 

**23. şekil — s.57**
- caption: Figure 5: Example of a potentially risky task GPT-4 augmented with tools can accomplish
- açıklama (DescriptionAnnotation): Prompt.

**24. şekil — s.63**
- caption: Figure 6: Example Prompt for RBRM
- açıklama (DescriptionAnnotation): Example prompt (full prompt in appendix).

**25. şekil — s.63**
- caption: Figure 7: Safety metrics on a challenging set of prompts that attempt to elicit unsafe or sensitive (e.g., regulated medical advice) outputs. Left: Rate of incorrect behavior on sensitive and disallowed prompts. Lower values are better. GPT-4-launch has much lower incorrect behavior rate compared to
- açıklama (DescriptionAnnotation): The right-hand side of the graph shows the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the next-day-divisi-tion-rate (n-dri) for the

**26. şekil — s.65**
- açıklama (DescriptionAnnotation): The figure shows the accuracy of questions on the Truthful IQQA MC1 as a percentage of the total.

**27. şekil — s.67**
- caption: Figure 9: Example Prompt for GPT-4 Classification in Natural Language
- açıklama (DescriptionAnnotation): Figure shows content warning: contains graphic erotic content.

**28. şekil — s.68**
- caption: Figure 10: Example "Jailbreaks" for GPT-4-launch
- açıklama (DescriptionAnnotation): Figure shows axis labels, legends, numbers, table cells and captions.

**29. şekil — s.98**
- caption: Figure 11: Results on IF evaluations across GPT3.5, GPT3.5-Turbo, GPT-4-launch
- açıklama (DescriptionAnnotation): The x-axis represents the lose rate while the y-axis represents the win rate.

## taranmis_bert_2sutun_dipnot — 2 şekil, 2 açıklandı

**1. şekil — s.3**
- caption: -Ii s  sr g o r i os ud -  -ons Bn :  vtis tures are used in both pre-training and fine-tuning. The same pre-trained model parameters are used to initialize models for different down-stream tasks. During fine-tuning, all parameters are fine-tuned. [CLS] is a special -y ades   a ds  s     p      poes
- açıklama (DescriptionAnnotation): The figures show pre-training and fine-tuning.

**2. şekil — s.5**
- caption: Figure 2: BERT input representation. The input embeddings are the sum of the token embeddings, the segmentation embeddings and the position embeddings.
- açıklama (DescriptionAnnotation): Input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input, input
