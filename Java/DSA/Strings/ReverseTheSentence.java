package DSA.Strings;

public class ReverseTheSentence {

    public static String reverseTheSentence(String sentence) {
        int left = 0;
        int right = sentence.length() - 1;

        String revSentence = "";

        while (right >= 0) {
            revSentence = revSentence + sentence.charAt(right);

            right--;
        }

        sentence = "";

        for (int i = 0; i < revSentence.length(); i++) {

            if (i == (revSentence.length() - 1) || revSentence.charAt(i) == ' ') {

                if (i == revSentence.length() - 1)
                    right = i;
                else
                    right = i - 1;

                while (left <= right) {
                    sentence = sentence + revSentence.charAt(right);
                    right--;
                }
                sentence = sentence + " ";
                left = i + 1;
            }

        }

        return sentence.trim();
    }

    public static void main(String[] args) {
        String sentence1 = "This is my sentence";

        System.out.print(reverseTheSentence(sentence1));
    }
}
